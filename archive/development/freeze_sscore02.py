import subprocess,sys
from pathlib import Path
W=Path(__file__).resolve().parent.parent;R=W/'outputs/PLM-L1-SS-core-v0.2';sys.path.insert(0,str(R))
from evaluation.integrity import write,read,freeze,preserve,sha
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=R,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 53 tests' in p.stderr,p.stderr
write(R/'verification/PREFLIGHT_TESTS.json',{'passed':True,'tests':53,'stdout':p.stdout,'stderr':p.stderr})
write(R/'verification/PRESERVATION.json',preserve())
dev=W/'work/sscore02-development'
write(R/'verification/DEVELOPMENT.json',{'trials':56,'summary':read(dev/'SUMMARY.json'),'decision':read(dev/'DECISION.json'),
    'policy_changed_after_development':False,'note':'Development primary superiority for pre_shared16 is unproven: single had no failed target in two development trials. Final criteria remain unchanged.'})
print({'frozen':freeze(),'tests':53},flush=True)
