import argparse,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.cases import build
from evaluation.experiment import run_case
from evaluation.channel import channel
from evaluate import summarize,acceptance
from bridge.carrier import encode
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory

def hashes(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and p.name!='PERFORMANCE.json'}
def minimal(folder):
    packages={'bridge':['__init__.py','carrier.py','recovery.py','runtime.py','__main__.py'],
       'ss_reconfirm':['__init__.py','session.py','runtime.py'], 'ss_revision':['__init__.py','context.py','memory.py'],
       'ss_retention':['__init__.py','context.py','memory.py'],'ss_partial':['__init__.py','contract.py','codec.py','runtime.py','update.py'],
       'ss_document':['__init__.py','contract.py','codec.py','runtime.py'],'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
       'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    s='vendor/PLM-S1-v0.2';old=s+'/vendor/PLM-S1-v0.1';p=old+'/vendor/PLM-P1-v0.2'
    packages.update({s+'/plm_s1_v02':['__init__.py','link.py','receiver.py','packet.py'],old+'/plm_s1':['__init__.py','link.py'],
                     p+'/plm_p1_v02':['__init__.py','recovery.py'],p+'/vendor/PLM-P1-v0.1/plm_p1':['__init__.py','core.py','packet.py']})
    for package,names in packages.items():
        target=folder/package;target.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copy2(ROOT/package/name,target/name)
    shutil.copytree(ROOT/'model',folder/'model');shutil.copy2(ROOT/'verification/isolated_cli.py',folder/'run.py')

def run(out,repeat=None):
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False);data=read(ROOT/'data/CORPUS.json');assert build()==data
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and 'Ran 40 tests' in p.stderr,p.stderr;write(out/'TESTS.json',{'passed':True,'stdout':p.stdout,'stderr':p.stderr})
    index=read(ROOT/'results/INDEX.json');model=PartialModel.load(ROOT/'model');cases={c['id']:c for c in data['splits']['evaluation']};rows=[];selected={};memories=0
    for name in index['runs']:
        r=read(ROOT/'results/runs'/name/'RESULT.json');memory=RevisionMemory.load(ROOT/'results/runs'/name/'memory',model.codec.candidates)
        assert memory.fingerprint==r['memory_fingerprint'];memories+=1;rows.append(r)
        selected.setdefault((r['condition'],r['method'],r['count']),(name,r))
        if r['teacher_learned']:
            assert memory.cost()['confirmed_targets']==2 and len(r['teacher']['receipts'])==2
        else:assert memory.cost()['confirmed_targets']==0
        assert not r['result']['nonmutable_changed'] and r['result']['fresh_session_no_receipts']
    assert summarize(rows)==read(ROOT/'results/SUMMARY.json')
    assert acceptance(summarize(rows),read(ROOT/'evaluation/PROTOCOL.json'))==read(ROOT/'results/DECISION.json')
    for i,(name,r) in enumerate(selected.values()):
        result=run_case(model,cases[r['case_id']],r['condition'],r['channel_seed'],r['method'],out/'replayed'/name)
        assert result==r,'replay_changed:'+name
        assert hashes(out/'replayed'/name/'memory')==hashes(ROOT/'results/runs'/name/'memory')
        if (i+1)%10==0:print({'replayed':i+1,'total':len(selected)},flush=True)
    repeated=None
    if repeat:
        h=hashes(ROOT/'results');assert h==hashes(Path(repeat));repeated=len(h);write(out/'REPEATABILITY.json',{'passed':True,'files':h,'excluded':['PERFORMANCE.json']})
    isolates=[]
    for n in (2,3):
        r=next(r for r in rows if r['count']==n and r['condition']=='partial25' and r['method']=='ss_estimated');case=cases[r['case_id']]
        name=next(name for name,row in zip(index['runs'],rows) if row is r);folder=out/f'isolated{n}';folder.mkdir();minimal(folder)
        shutil.copytree(ROOT/'results/runs'/name/'memory',folder/'memory');write(folder/'scope.json',case['scope'])
        mid=case['id']+'/query';wire,_=channel(model,encode(model,model.encode(case['query']),mid),r['condition'],r['channel_seed']+10000)
        write(folder/'received.json',wire)
        p=subprocess.run([sys.executable,'-I','-B','-X','utf8','run.py','generate','--model','model','--memory','memory','--scope','scope.json',
                         '--wire','received.json','--message-id',mid],cwd=folder,capture_output=True,text=True,encoding='utf-8')
        assert p.returncode in (0,2),p.stderr;g=json.loads(p.stdout);provenance=json.loads(p.stderr)
        if r['result']['status']=='generated':
            assert g['status']=='generated' and g['text']==r['result']['outputs'][0]['generation']['text']
            assert g['reception']['despread_signal_sha256']==r['query']['despread_signal_sha256'] and g['fresh_session_no_receipts']
        else:assert g['status']!='generated'
        isolates.append({'case_id':case['id'],'count':n,'result':g,'provenance':provenance})
    write(out/'ISOLATED.json',isolates)
    copied=read(ROOT/'verification/PREVIOUS.json')['copied']
    for name,r in copied.items():assert sha(ROOT/name)==r['sha256']
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        h={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert h==read(ROOT/'RELEASE_MANIFEST.json')['files'];manifest=len(h)
    record={'passed':True,'frozen_digest':frozen,'tests':40,'saved_memories_loaded':memories,'representative_full_replays':len(selected),
            'all_summaries_recomputed':True,'corpus_rebuilt_exactly':True,'full_repeat_equal_files':repeated,'copied_files_unchanged':len(copied),
            'isolated_queries':2,'isolated_generated':sum(r['result']['status']=='generated' for r in isolates),'manifest_files_checked':manifest,
            'numerical_acceptance_passed':read(ROOT/'results/DECISION.json')['passed'],'eligible_for_inference':False}
    write(out/'VERIFY.json',record);print(json.dumps(record,indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--repeat');a=p.parse_args();run(a.out,a.repeat)
