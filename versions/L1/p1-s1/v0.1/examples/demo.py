import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write
from evaluation.channel import channel
from bridge.carrier import encode,demodulate
from bridge.recovery import recover_masked
from ss_partial.runtime import PartialModel
from ss_partial.contract import from_meaning

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);model=PartialModel.load(ROOT/'model');cases=read(ROOT/'data/CORPUS.json')['splits']['evaluation'][:2];rows=[];arrays={}
    for i,case in enumerate(cases):
        folder=out/f'case{i}';folder.mkdir();source=model.document.read(case['text']);assert source['status']=='read'
        meaning=model.document.recover(source['packet'])['meaning'];known=from_meaning(meaning,model.codec.candidates);assert known==case['known']
        write(folder/'source.json',{'text':case['text'],'reader_output_equal':True,'known':known,'query':case['query']});write(folder/'scope.json',case['scope'])
        for j,(kind,o) in enumerate((('teacher',known),('query',case['query']))):
            packet=model.encode(o);mid=case['id']+'/'+kind;tx=encode(model,packet,mid);wire,truth=channel(model,tx,'partial25',2100+10000*j)
            write(folder/f'{kind}-transmitted.json',tx);write(folder/f'{kind}-received.json',wire);write(folder/f'{kind}-channel-truth.json',truth)
            vector,mask,_=demodulate(model,wire,mid);recovered,audit=recover_masked(model,vector,mask)
            arrays[f'case{i}-{kind}-source']=model.vector(packet);arrays[f'case{i}-{kind}-despread']=vector;arrays[f'case{i}-{kind}-mask']=mask;arrays[f'case{i}-{kind}-recovered']=model.vector(recovered)
        base=[sys.executable,'-B','-m','bridge'];common=['--model',str(ROOT/'model'),'--scope',str(folder/'scope.json')]
        commands=[['learn',*common,'--wire',str(folder/'teacher-received.json'),'--message-id',case['id']+'/teacher','--out',str(folder/'memory')]]
        commands += [['generate',*common,'--memory',str(folder/'memory'),'--wire',str(folder/'query-received.json'),'--message-id',case['id']+'/query','--order',order] for order in ('preserve','reverse')]
        results=[]
        for command in commands:
            p=subprocess.run(base+command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode in (0,2),p.stderr
            results.append({'command':command,'exit_code':p.returncode,'result':json.loads(p.stdout)})
        write(folder/'CLI.json',results);rows.append({'case_id':case['id'],'count':case['known']['count'],'input_text':case['text'],'learned':results[0]['result']['status']=='learned',
             'outputs':[{'status':r['result']['status'],'text':r['result'].get('text'),'no_receipts':r['result'].get('fresh_session_no_receipts')} for r in results[1:]]})
    np.savez_compressed(out/'REFERENCE_SIGNALS.npz',**arrays);write(out/'DEMO.json',rows);print(json.dumps(rows,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
