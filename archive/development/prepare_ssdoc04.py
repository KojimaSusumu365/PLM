import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-SS-doc-v0.4';sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,freeze
from evaluation.revision_cases import cases,prepared_data
from evaluation.revision_experiment import query
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory,METHODS
from ss_revision.learning import learn

model=PartialModel.load(ROOT/'model');data=cases('development',True);records=prepared_data(model,data);rows=[]
for name in METHODS:
    m=RevisionMemory(model.codec.candidates,name,'revision-development')
    for r in records:m.register(r['root'],r['targets'],r['kind']=='focal')
    for step in range(5):
        for r in records[:8]:learn(m,r['teachers'][step]['prepared'])
    for step in range(2):
        for r in records[8:]:learn(m,r['teachers'][step]['prepared'])
    rows.extend({'method':name,**query(model,m,c)} for c in data[:8])
    print({'method':name,'correct':sum(r['correct'] for r in rows if r['method']==name)},flush=True)
write(ROOT/'verification/DEVELOPMENT.json',{'rows':rows,'data':data,'note':'48 queries; development only; no final outcome tuning.'})
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0,p.stderr
write(ROOT/'verification/TESTS.json',{'passed':True,'stdout':p.stdout,'stderr':p.stderr,'returncode':p.returncode})
freeze();print({'development_complete':True,'tests_passed':True,'frozen':True},flush=True)
