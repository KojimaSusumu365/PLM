import argparse,os,platform,shutil,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify

def run(verifier,work):
    verifier=Path(verifier);work=Path(work);work.mkdir(parents=True,exist_ok=False);assert read(verifier/'VERIFY.json')['passed']
    for name in ('VERIFY.json','REPEATABILITY.json','SELECTOR_RETRAINING.json','ISOLATED.json'):
        assert not (ROOT/'verification'/name).exists();shutil.copy2(verifier/name,ROOT/'verification'/name)
    from verification.summarize import run as summarize
    from verification.log_audit import run as audit
    summarize();audit()
    from examples.demo import run as demo
    from verification.cli_workflow import run as cli
    from verification.measure_cost import run as cost
    demo(ROOT/'examples/run');cli(work/'cli');cost()
    old=read(ROOT/'verification/PREVIOUS_BASELINE.json');previous=ROOT.parent/old['release']
    actual={p.relative_to(previous).as_posix():sha(p) for p in previous.rglob('*') if p.is_file()}
    assert actual==old['files'] and sha(previous.with_name(previous.name+'.zip'))==old['zip_sha256']
    assert all(sha(ROOT/name)==h for name,h in old['copied_files'].items())
    write(ROOT/'verification/PRESERVATION.json',{'passed':True,'previous_files_unchanged':len(actual),'previous_zip_unchanged':True,
             'copied_files_unchanged':len(old['copied_files']),'language_model_unchanged':True,'v05_generation_gate_unchanged':True})
    env=dict(os.environ);env['OPENBLAS_NUM_THREADS']='1';env['PYTHONIOENCODING']='utf-8';env.pop('PYTHONPATH',None)
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and 'Ran 116 tests' in p.stderr,p.stderr
    write(ROOT/'verification/FINAL_TESTS.json',{'passed':True,'tests':116,'stdout':p.stdout,'stderr':p.stderr})
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'executable':sys.executable,'numpy':np.__version__,'platform':platform.platform(),
              'OPENBLAS_NUM_THREADS':os.environ.get('OPENBLAS_NUM_THREADS'),'evaluation_seconds':read(ROOT/'results/PERFORMANCE.json')['seconds'],
              'selector_training_seconds':read(ROOT/'training_results/PERFORMANCE.json')['seconds']})
    print({'passed':True,'tests':116,'frozen':verify()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verifier',required=True);p.add_argument('--work',required=True);a=p.parse_args();run(a.verifier,a.work)
