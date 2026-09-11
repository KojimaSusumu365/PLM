"""Exercise actual CLI processes and immutable output destinations."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);demo=ROOT/'examples/run';calls=[]
    env=dict(os.environ);env['OPENBLAS_NUM_THREADS']='1';env['PYTHONIOENCODING']='utf-8';env.pop('PYTHONPATH',None)
    def call(args,code=0):
        p=subprocess.run([sys.executable,'-B','-m','ss_reconfirm',*map(str,args)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        assert p.returncode==code,p.stderr
        obj=json.loads(p.stdout);calls.append({'arguments':list(map(str,args)),'returncode':p.returncode,'result':obj});return obj
    base=['--model',ROOT/'model','--memory',demo/'before-memory']
    call(['start',*base,'--scope',demo/'scope.json','--packet',demo/'input-packet.json','--out',out/'session.json'])
    plan=call(['plan',*base,'--session',out/'session.json'],2)
    assert plan==read(demo/'DEMO.json')['initial_plan']
    call(['generate',*base,'--session',out/'session.json'],2)
    call(['confirm',*base,'--session',out/'session.json','--answer',demo/'answer.json','--out',out/'confirmed.json','--memory-out',out/'memory'])
    updated=['--model',ROOT/'model','--memory',out/'memory']
    generated=call(['generate',*updated,'--session',out/'confirmed.json'])
    assert generated==read(demo/'DEMO.json')['immediate']
    call(['start',*updated,'--scope',demo/'scope.json','--packet',demo/'cold-packet.json','--out',out/'cold.json'])
    assert read(out/'cold.json')['payload']['confirmed']=={}
    cold=call(['generate',*updated,'--session',out/'cold.json'])
    assert cold==read(demo/'DEMO.json')['cold_without_receipts']
    result={'passed':True,'processes':len(calls),'calls':calls,'eligible_for_inference':False}
    write(ROOT/'verification/CLI_WORKFLOW.json',result);return result

if __name__=='__main__':run(sys.argv[1])
