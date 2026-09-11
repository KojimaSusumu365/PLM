import subprocess
import sys
from pathlib import Path
W = Path(__file__).resolve().parent.parent
R = W/'outputs/PLM-L1-SS-core-v0.1'
sys.path.insert(0,str(R))
from evaluation.integrity import freeze,preserve,write
p = subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=R,
                   capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 30 tests' in p.stderr,p.stderr
write(R/'verification/PREFLIGHT_TESTS.json',{'passed':True,'tests':30,'stdout':p.stdout,'stderr':p.stderr})
write(R/'verification/PREFLIGHT_PRESERVATION.json',preserve())
print({'frozen':freeze(),'tests':30},flush=True)
