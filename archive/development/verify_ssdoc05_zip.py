import json,os,subprocess,sys
from pathlib import Path
WORK=Path(__file__).resolve().parent;package=json.loads((WORK/'ssdoc05-package.json').read_text(encoding='utf-8'))
ROOT=Path(package['extracted_root']);sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha
env=dict(os.environ);env['OPENBLAS_NUM_THREADS']='1';env['PYTHONIOENCODING']='utf-8';env.pop('PYTHONPATH',None)
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 86 tests' in p.stderr,p.stderr
tests={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr};out=WORK/'ssdoc05-zip-verifier'
p=subprocess.run([sys.executable,'-B','verify_release.py','--out',str(out),'--repeat',str(WORK/'ssdoc05-repeat')],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0,p.stderr
r=read(out/'VERIFY.json');assert r['passed'] and r['manifest_files_checked']==package['manifest_files']
assert sha(Path(package['archive']))==package['archive_sha256']
write(WORK.parent/'outputs/PLM-L1-SS-doc-v0.5-POSTZIP.json',{'passed':True,'package':package,'tests':tests,'verifier':r,'isolated':read(out/'ISOLATED.json'),
      'scope':'All extracted hashes;86 tests;144 closed-loop prefix episodes and144 fresh cold probes;all reference arrays;8 base and72 final states;full second-run comparison and isolated inference. Not a third full evaluation.',
      'eligible_for_inference':False})
print(json.dumps({'passed':True,'tests':86,'verifier':r},indent=2),flush=True)
