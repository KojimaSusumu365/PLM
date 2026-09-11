import subprocess,sys
from pathlib import Path
W=Path(__file__).resolve().parent.parent;R=W/'outputs/PLM-L1-SS-core-v0.2';sys.path.insert(0,str(R))
from evaluation.integrity import write,preserve
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=W/'outputs/PLM-L1-SS-core-v0.1',
                 capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 30 tests' in p.stderr,p.stderr
write(R/'verification/PRIOR_TESTS.json',{'passed':True,'tests':30,'release':'PLM-L1-SS-core-v0.1',
    'stdout':p.stdout,'stderr':p.stderr,'scope':'Original release own suite only, overlapping the 30 inherited tests in the current 53-test suite.'})
write(R/'verification/FINAL_PRESERVATION.json',preserve())
print({'previous_tests':30,'passed':True},flush=True)
