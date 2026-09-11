import json,os,subprocess,sys
from pathlib import Path
WORK=Path(__file__).resolve().parent;package=json.loads((WORK/'bridge01-package.json').read_text(encoding='utf-8'));ROOT=Path(package['extracted_root']);sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha
env=dict(os.environ);env['OPENBLAS_NUM_THREADS']='1';env['PYTHONIOENCODING']='utf-8';env.pop('PYTHONPATH',None)
out=WORK/'bridge01-zip-verifier';p=subprocess.run([sys.executable,'-B','verify_release.py','--out',str(out),'--repeat',str(WORK/'bridge01-repeat')],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0,p.stderr
r=read(out/'VERIFY.json');assert r['passed'] and r['manifest_files_checked']==package['manifest_files'] and r['numerical_acceptance_passed']
assert sha(Path(package['archive']))==package['archive_sha256']
write(WORK.parent/'outputs/PLM-L1-P1-S1-v0.1-POSTZIP.json',{'passed':True,'package':package,'verifier':r,'tests':read(out/'TESTS.json'),
    'isolated':read(out/'ISOLATED.json'),'scope':'40 tests; all388 saved memories;44 full representative signal/teacher/learning/query/generation replays;corpus rebuild;all evaluation-repeat files;two isolated cold generations;manifest. Not a third full388-condition evaluation.',
    'eligible_for_inference':False})
print(json.dumps({'passed':True,'verifier':r,'package':package},indent=2),flush=True)
