import subprocess,sys
from pathlib import Path
W=Path(__file__).resolve().parent.parent;R=W/'work/sscore02-zip-extracted/PLM-L1-SS-core-v0.2'
sys.path.insert(0,str(R))
from evaluation.integrity import read,write,sha
package=read(R.parent/'PACKAGE.json');out=W/'work/sscore02-zip-verifier'
p=subprocess.run([sys.executable,'-B','verify_release.py','--out',str(out),'--repeat',str(W/'work/sscore02-repeat')],
                 cwd=R,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0,p.stderr+'\n'+p.stdout
verify=read(out/'VERIFY.json');assert verify['passed']
q=subprocess.run([sys.executable,'-B','verification/qa_examples.py',str(out/'EXAMPLES_QA.json')],cwd=R,
                 capture_output=True,text=True,encoding='utf-8')
assert q.returncode==0,q.stderr
assert sha(Path(package['zip']))==package['zip_sha256']
record={'passed':True,'package':package,'extracted_release_verification':verify,'examples':read(out/'EXAMPLES_QA.json'),
    'verification_returncode':p.returncode,'verification_stdout':p.stdout,'verification_stderr':p.stderr,
    'zip_hash_unchanged_after_verification':True,'important':'Primary checks and artifact integrity do not establish safety against shared corruption or false teachers.'}
write(W/'outputs/PLM-L1-SS-core-v0.2-POSTZIP.json',record)
print({k:v for k,v in record.items() if k not in ('verification_stdout','verification_stderr')},flush=True)
