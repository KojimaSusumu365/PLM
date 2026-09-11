import argparse,json,os,platform,shutil,statistics,subprocess,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import assess,generate

def run(verifier,work):
    verifier=Path(verifier);work=Path(work);work.mkdir(parents=True,exist_ok=False)
    assert read(verifier/'VERIFY.json')['passed']
    for name in ('VERIFY.json','REPEATABILITY.json','ISOLATED.json'):
        assert not (ROOT/'verification'/name).exists();shutil.copy2(verifier/name,ROOT/'verification'/name)
    from examples.demo import run as demo
    demo(ROOT/'examples/run')
    from verification.cli_workflow import run as cli
    cli(work/'cli')
    from verification.summarize import run as summary
    summary()
    from verification.log_audit import run as audit
    audit()
    old=read(ROOT/'verification/PREVIOUS_BASELINE.json');previous=ROOT.parent/old['release']
    actual={p.relative_to(previous).as_posix():sha(p) for p in previous.rglob('*') if p.is_file()}
    assert actual==old['files'] and sha(previous.with_name(previous.name+'.zip'))==old['zip_sha256']
    assert all(sha(ROOT/name)==h for name,h in old['copied_files'].items())
    write(ROOT/'verification/PRESERVATION.json',{'passed':True,'previous_files_unchanged':len(actual),
          'previous_zip_unchanged':True,'copied_files_unchanged':len(old['copied_files']),'language_model_unchanged':True})
    env=dict(os.environ);env['OPENBLAS_NUM_THREADS']='1';env['PYTHONIOENCODING']='utf-8';env.pop('PYTHONPATH',None)
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and 'Ran 86 tests' in p.stderr,p.stderr
    write(ROOT/'verification/FINAL_TESTS.json',{'passed':True,'tests':86,'stdout':p.stdout,'stderr':p.stderr})
    model=PartialModel.load(ROOT/'model');folder=ROOT/'examples/run';m=RevisionMemory.load(folder/'after-memory',model.codec.candidates)
    s=Session.load(folder/'cold-session.json',model,m);fp=m.fingerprint;packet=read(folder/'cold-packet.json');mf=model.fingerprint
    timing={}
    for name,fn in [('assess',lambda:assess(model,m,s)),('generate',lambda:generate(model,m,s))]:
        fn();samples=[]
        for _ in range(7):
            start=time.perf_counter();fn();samples.append((time.perf_counter()-start)*1000)
        timing[name]={'milliseconds':samples,'median_ms':statistics.median(samples)}
    assert m.fingerprint==fp and model.fingerprint==mf and s.packet==packet
    m.save(work/'roundtrip-memory')
    hashes=lambda d:{p.relative_to(d).as_posix():sha(p) for p in d.rglob('*') if p.is_file()}
    assert hashes(folder/'after-memory')==hashes(work/'roundtrip-memory')
    write(ROOT/'verification/INFERENCE_AUDIT.json',{'passed':True,'persistent_memory_unchanged':True,'numeric_input_unchanged':True,
         'model_fingerprint_unchanged':True,'persistent_save_roundtrip_equal_files':3,'timing':timing,
         'timing_scope':'one small demonstration, one warmup then seven samples; not a cross-method performance comparison',
         'ss_coefficient_bytes':m.cost()['total_coefficient_bytes'],'memory_cost':m.cost(),'frozen_digest':verify()})
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'executable':sys.executable,'numpy':np.__version__,
         'platform':platform.platform(),'OPENBLAS_NUM_THREADS':os.environ.get('OPENBLAS_NUM_THREADS'),
         'original_evaluation_seconds':read(ROOT/'results/PERFORMANCE.json')['seconds']})
    print(json.dumps({'passed':True,'tests':86,'previous_files':len(actual),'frozen':verify()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verifier',required=True);p.add_argument('--work',required=True);a=p.parse_args();run(a.verifier,a.work)
