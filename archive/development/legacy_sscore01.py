import subprocess
import sys
from pathlib import Path
W=Path(__file__).resolve().parent.parent
R=W/'outputs/PLM-L1-SS-core-v0.1'
sys.path.insert(0,str(R))
from evaluation.integrity import write,preserve
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],
                 cwd=W/'outputs/PLM-L1-P1-S1-v0.1',capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 40 tests' in p.stderr,p.stderr
write(R/'verification/PRIOR_BRIDGE_TESTS.json',{'release':'PLM-L1-P1-S1-v0.1','passed':True,'tests':40,
    'scope':'Original bridge release directory, not all historical suites','stdout':p.stdout,'stderr':p.stderr})
write(R/'verification/FINAL_PRESERVATION.json',preserve())
print({'previous_bridge_tests':40,'passed':True},flush=True)
