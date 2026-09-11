import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'examples/run';calls=[]
    env=dict(os.environ);env['OPENBLAS_NUM_THREADS']='1';env['PYTHONIOENCODING']='utf-8';env.pop('PYTHONPATH',None)
    def call(module,args):
        p=subprocess.run([sys.executable,'-B','-m',module,*map(str,args)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
        r=json.loads(p.stdout);calls.append({'module':module,'args':list(map(str,args)),'returncode':p.returncode,'result':r});return r
    base=['--model',ROOT/'model','--memory',d/'before-memory','--workset',d/'workset.json']
    chosen=call('ss_select',['choose',*base,'--selector',ROOT/'data/selector_model']);assert chosen==read(d/'DEMO.json')['selection']
    receipt=call('ss_select',['confirm',*base,'--answer',d/'answer.json','--out',out/'memory']);assert receipt==read(d/'DEMO.json')['receipt']
    call('ss_reconfirm',['start','--model',ROOT/'model','--memory',out/'memory','--scope',d/'scope.json','--packet',d/'fresh-packet.json','--out',out/'session.json'])
    assert read(out/'session.json')['payload']['confirmed']=={}
    g=call('ss_reconfirm',['generate','--model',ROOT/'model','--memory',out/'memory','--session',out/'session.json']);assert g==read(d/'DEMO.json')['cold_generation']
    result={'passed':True,'processes':len(calls),'calls':calls,'eligible_for_inference':False};write(ROOT/'verification/CLI_WORKFLOW.json',result);return result

if __name__=='__main__':run(sys.argv[1])
