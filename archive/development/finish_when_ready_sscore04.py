"""Continue this build pipeline after its finite evaluation process finishes."""
import os,subprocess,sys,time
from pathlib import Path
base=Path(__file__).resolve().parents[1];root=base/'outputs/PLM-L1-SS-core-v0.4'
env={**os.environ,'OPENBLAS_NUM_THREADS':'1','PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'}
started=time.monotonic()
while not (root/'results/PARALLEL.json').exists():
    if time.monotonic()-started>7200:raise TimeoutError('evaluation did not finish within two hours')
    time.sleep(2)
print('Evaluation finished; checking repeat, rebuild and isolated generation.',flush=True)
subprocess.run([sys.executable,'-X','utf8','-B','-m','evaluation.reproduce04','--output','verification/REPRODUCTION04.json'],cwd=root,env=env,check=True)
print('Reproduction passed; creating report, ZIP and testing extracted ZIP.',flush=True)
subprocess.run([sys.executable,'-X','utf8','-B',str(base/'work/finalize_sscore04.py')],cwd=base,env=env,check=True)
