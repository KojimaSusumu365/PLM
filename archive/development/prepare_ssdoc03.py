import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-SS-doc-v0.3';sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,freeze
from evaluation.cases import dataset
from evaluation.experiment import teacher_records,train,query
from ss_partial.runtime import PartialModel
from ss_retention.memory import CorrectionMemory

model=PartialModel.load(ROOT/'model');data=dataset('development',True);teachers=teacher_records(model,data);rows=[]
for method in ('shared736','shared1472','split_pair','split_bank'):
    memory=CorrectionMemory(model.codec.candidates,method,'development-code')
    immediate,held=train(memory,teachers,32)
    for c in data[:8]:
        r=query(model,memory,c,'unobserved');rows.append({'method':method,**r})
        assert r['final_equal'] and all(g['score']['semantic_equal'] for g in r['outputs']),r
write(ROOT/'verification/DEVELOPMENT.json',{'passed':True,'rows':rows,'data':data,'note':'32 reacquisition trials; no final-results tuning.'})
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0,p.stderr
write(ROOT/'verification/TESTS.json',{'passed':True,'stdout':p.stdout,'stderr':p.stderr,'returncode':p.returncode})
freeze();print({'passed':True,'development_requeries':len(rows),'tests':32,'frozen':True},flush=True)
