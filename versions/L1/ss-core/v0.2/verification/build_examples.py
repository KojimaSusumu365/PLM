"""Real separate-process CLI example, plus recorded fault-injected read windows."""
import json,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify
from evaluation.faults import Acquisitions
from evaluation.oracle import localize,scored
from ss_partial.runtime import PartialModel
from ss_core_v02.store import Store
from ss_core_v02.transaction import apply_received
from ss_core.clock import ReadWindow
from bridge.carrier import encode

def cli(args,expected):
    p=subprocess.run([sys.executable,'-B','-m','ss_core_v02',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==expected,p.stderr
    return json.loads(p.stdout)

def main():
    frozen=verify();model=PartialModel.load(ROOT/'model')
    c=next(c for c in read(ROOT/'data/GUARD_CORPUS.json')['splits']['evaluation'] if c['id']=='evaluation/focal/3')
    folder=ROOT/'examples/reconfirmation';folder.mkdir(exist_ok=False)
    write(folder/'scope.json',c['scope']);write(folder/'SOURCE.json',c)
    for kind,o in [('initial',c['initial']),('final',c['known']),('query',c['query'])]:
        write(folder/(kind+'-wire.json'),encode(model,model.encode(o),'demo02/'+kind))
    common=['--model',str(ROOT/'model'),'--scope',str(folder/'scope.json')]
    initial=cli(['learn',*common,'--wire',str(folder/'initial-wire.json'),'--message-id','demo02/initial',
                 '--out',str(folder/'initial-store')],0)
    write(folder/'INITIAL_LEARN.json',initial)
    store=Store.load(folder/'initial-store',model.codec.candidates)
    port=Acquisitions('independent16',99001);captured=[]
    def capture(part,key,nonce):
        events=list(port(part,key,nonce));captured.append({'part':part.seed,'key':key,'nonce':nonce,'events':events})
        yield from events
    held,receipt=apply_received(model,store,c['scope'],read(folder/'final-wire.json'),'demo02/final',port_factory=capture)
    assert receipt['status']=='held' and held.memory.fingerprint==store.memory.fingerprint
    held.save(folder/'held-store');write(folder/'HELD_UPDATE.json',receipt)
    arrays={};logs=[]
    for i,item in enumerate(captured):
        part=next(p for p in store.memory.ss.parts.values() if p.seed==item['part'])
        w=ReadWindow(part,item['key'],item['nonce'],True)
        w.push_many(item['events']);scores,audit=w.finish()
        arrays[f'window{i}_samples']=np.stack([e[1] for e in item['events']])
        arrays[f'window{i}_observed']=np.stack([e[2] for e in item['events']])
        logs.append({'part_seed':item['part'],'key':item['key'],'nonce':item['nonce'],'audit':audit,'scores':scores.tolist()})
    np.savez_compressed(folder/'noisy-read-windows.npz',**arrays)
    write(folder/'WINDOWS.json',logs)
    waiting=cli(['generate',*common,'--wire',str(folder/'query-wire.json'),'--message-id','demo02/query',
                 '--memory',str(folder/'held-store')],2)
    assert waiting['status']=='needs_confirmation' and 'text' not in waiting
    write(folder/'COLD_PENDING.json',waiting)
    confirmed=cli(['learn',*common,'--wire',str(folder/'final-wire.json'),'--message-id','demo02/final',
                   '--memory',str(folder/'held-store'),'--out',str(folder/'confirmed-store')],0)
    write(folder/'CONFIRMED_UPDATE.json',confirmed)
    outputs=[]
    for order,goals in [('preserve',['subject','subject']),('reverse',['object','subject'])]:
        r=cli(['generate',*common,'--wire',str(folder/'query-wire.json'),'--message-id','demo02/query',
               '--memory',str(folder/'confirmed-store'),'--order',order,'--goals',*goals],0)
        ids=c['meaning']['presentation'][::1 if order=='preserve' else -1]
        result=scored(localize(c['meaning'],ids,goals),r['text']);assert all(result.values())
        write(folder/(order+'-GENERATE.json'),r)
        outputs.append({'order':order,'text':r['text'],'score':result})
    write(ROOT/'examples/INDEX.json',{'frozen_digest':frozen,'case_id':c['id'],'initial_text':c['initial_text'],
        'corrected_text':c['text'],'missing_targets':c['scope']['mutable'],'pending_status':waiting['status'],
        'separate_cli_processes':5,'recorded_read_windows':len(logs),'outputs':outputs,'eligible_for_inference':False})
    print({'example_completed':True,'pending_then_reconfirmed':True,'generated':len(outputs)},flush=True)

if __name__=='__main__':main()
