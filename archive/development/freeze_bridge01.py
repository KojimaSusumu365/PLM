import shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent/'outputs/PLM-L1-P1-S1-v0.1';sys.path.insert(0,str(R))
from evaluation.integrity import write,preserve,freeze,ROOT,read
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=R,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 40 tests' in p.stderr,p.stderr
write(R/'verification/INITIAL_TESTS.json',{'passed':True,'stdout':p.stdout,'stderr':p.stderr})
write(R/'verification/PRESERVATION.json',preserve())
development=R.parents[1]/'work/bridge01-development-a'
write(R/'verification/DEVELOPMENT.json',{'runs':88,'summary':read(development/'SUMMARY.json'),'seconds':read(development/'PERFORMANCE.json')['seconds'],
      'scope':'Development corpus only. No thresholds or numerical methods changed after this run; main wrong-teacher audit acceptance was added before freeze.'})
print({'frozen':freeze(),'tests':40,'previous':preserve()},flush=True)
