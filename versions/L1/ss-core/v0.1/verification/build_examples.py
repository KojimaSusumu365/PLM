"""Generate auditable CLI examples after the frozen evaluation (not an evaluator input)."""
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify
from evaluation.channel import channel
from evaluation.oracle import localize,scored
from ss_partial.runtime import PartialModel
from ss_partial.contract import from_meaning
from ss_revision.memory import RevisionMemory
from ss_revision.context import address,scope_key
from ss_core.clock import ExactPort,ReadWindow
from bridge.carrier import encode

def cli(args):
    p=subprocess.run([sys.executable,'-B','-m','ss_core',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0,p.stderr
    return json.loads(p.stdout)

def main():
    frozen=verify()
    model=PartialModel.load(ROOT/'model')
    cases=read(ROOT/'data/CORPUS.json')['splits']['evaluation']
    focal=[c for c in cases if c['kind']=='focal']
    demos=[]
    for index in (0,4):
        case=focal[index]
        folder=ROOT/'examples'/f'demo-{index}'
        folder.mkdir(exist_ok=False)
        write(folder/'scope.json',case['scope'])
        r=model.document.read(case['text'])
        assert r['status']=='read'
        known=from_meaning(model.document.recover(r['packet'])['meaning'],model.codec.candidates)
        write(folder/'SOURCE.json',{'text':case['text'],'missing_targets':case['scope']['mutable'],
                                  'known':known,'query':case['query'],'source':'explicit external teacher','eligible_for_inference':False})
        ids={}
        for kind,obs in [('teacher',known),('query',case['query'])]:
            mid='ss-core01/'+case['id']+'/'+kind
            ids[kind]=mid
            seed=41000+cases.index(case)*97+(10000 if kind=='query' else 0)
            wire,truth=channel(model,encode(model,model.encode(obs),mid),'partial25',seed)
            write(folder/(kind+'-wire.json'),wire)
            write(folder/(kind+'-channel-truth.json'),{'parameters':truth,'eligible_for_inference':False})
        common=['--model',str(ROOT/'model'),'--scope',str(folder/'scope.json')]
        teaching=cli(['learn',*common,'--wire',str(folder/'teacher-wire.json'),'--message-id',ids['teacher'],
                      '--out',str(folder/'memory'),'--chunk','37'])
        write(folder/'LEARN.json',teaching)
        outputs=[]
        for order,goals in [('preserve',['subject','subject']),('reverse',['object','subject'])]:
            g=cli(['generate',*common,'--wire',str(folder/'query-wire.json'),'--message-id',ids['query'],
                   '--memory',str(folder/'memory'),'--order',order,'--goals',*goals,'--chunk','37'])
            positions=case['meaning']['presentation'][::1 if order=='preserve' else -1]
            score=scored(localize(case['meaning'],positions,goals),g['text'])
            assert all(score.values()) and g['fresh_session_no_receipts']
            write(folder/(order+'-GENERATE.json'),g)
            outputs.append({'order':order,'text':g['text'],'independent_score':score})
        memory=RevisionMemory.load(folder/'memory',model.codec.candidates)
        root,targets=scope_key(case['scope'],case['query'])
        key=address(memory.policy,root,targets[0],memory.roots[root]['versions'][targets[0]])
        waves,logs={},[]
        for name,part in memory.ss.parts.items():
            nonce='lookup/'+name
            window=ReadWindow(part,key,nonce)
            events=list(ExactPort(part,key,nonce))
            waves[name+'_samples']=np.stack([e[1] for e in events])
            waves[name+'_observed']=np.stack([e[2] for e in events])
            points=[]
            for event in events:
                window.push(*event)
                if event[0] in (0,15,16,383,751,759,767):
                    points.append({'tick':event[0],'peek':window.peek(),
                                   'accumulator_real_first_channel':window.acc[0].real.tolist()})
            scores,audit=window.finish()
            difference=float(np.max(abs(scores-part.scores(key))))
            assert difference<=1e-10 and all(not p['peek']['eligible_for_decision'] for p in points)
            logs.append({'part':name,'key':key,'target':targets[0],'progress':points,'final':audit,
                         'batch_score_max_abs_difference':difference})
        np.savez_compressed(folder/'internal-waveforms.npz',**waves)
        write(folder/'CLOCK_PROGRESS.json',logs)
        demos.append({'case_id':case['id'],'directory':folder.name,'source_text':case['text'],
                      'missing_targets':case['scope']['mutable'],'outputs':outputs,
                      'independent_processes':3,'saved_memory_fingerprint':memory.fingerprint})
    write(ROOT/'examples/INDEX.json',{'frozen_digest':frozen,'demos':demos,
        'note':'Standalone CLI teaching examples; main 23-document trained memories are separately stored under results/runs.'})
    print({'demonstrations':len(demos),'correct_generated_texts':sum(len(d['outputs']) for d in demos)},flush=True)

if __name__=='__main__':main()
