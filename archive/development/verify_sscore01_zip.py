import json
import subprocess
import sys
from pathlib import Path
W=Path(__file__).resolve().parent.parent
R=W/'work/sscore01-zip-extracted/PLM-L1-SS-core-v0.1'
sys.path.insert(0,str(R))
from evaluation.integrity import read,write,sha
package=read(R.parent/'PACKAGE.json')
out=W/'work/sscore01-zip-verifier'
p=subprocess.run([sys.executable,'-B','verify_release.py','--out',str(out),
                  '--repeat',str(W/'work/sscore01-repeat')],cwd=R,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0,p.stderr+'\n'+p.stdout
verification=read(out/'VERIFY.json')
assert verification['passed'] and verification['numerical_acceptance_passed'] is False
archive=Path(package['zip'])
assert sha(archive)==package['zip_sha256']
record={'package':package,'extracted_release_verification':verification,
        'verification_returncode':p.returncode,'verification_stdout':p.stdout,'verification_stderr':p.stderr,
        'zip_hash_unchanged_after_verification':True,'passed':True,
        'important':'Verification success does not mean all experimental criteria passed; one outer teacher remained held.'}
write(W/'outputs/PLM-L1-SS-core-v0.1-POSTZIP.json',record)
print(json.dumps({k:v for k,v in record.items() if k not in ('verification_stdout','verification_stderr')},indent=2),flush=True)
