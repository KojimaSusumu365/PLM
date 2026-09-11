import shutil,subprocess,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];ROOT=BASE/'outputs/PLM-L1-SS-doc-v0.6';sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,freeze
from evaluation.revision_cases import prepared_data
from evaluation.delay_experiment import initialize,background,slot_score,run_selection,document_probes
from ss_partial.runtime import PartialModel
from ss_select.memory import SelectorMemory
import copy
assert read(ROOT/'training_results/TRAINING.json')['examples']==576
shutil.copytree(ROOT/'training_results/model',ROOT/'data/selector_model')
model=PartialModel.load(ROOT/'model');selector=SelectorMemory.load(ROOT/'data/selector_model');ds=read(ROOT/'data/DELAY_DATASETS.json')['splits']['development']
records=prepared_data(model,ds['cases']);focal=ds['cases'][:6];rows=[]
for method in ('versioned_shared','versioned_pair'):
    base=initialize(model,records,method,'delay-development-06');background(base,records,0,64)
    for policy in ('rule','random','ss_learned'):
        current=copy.deepcopy(base);trace=run_selection(model,current,focal,policy,selector,6,'dev06')
        immediate=slot_score(current,focal,records);background(current,records,64,96);delayed,_=document_probes(model,current,focal)
        slots=slot_score(current,focal,records);assert all((a['correct'],a['wrong'])==(b['correct'],b['wrong']) for a,b in zip(delayed,slots))
        assert len(trace)==6
        rows.append({'method':method,'policy':policy,'trace':trace,'immediate':immediate,'delayed':delayed})
        print({'development':method,'policy':policy,'answers':len(trace),'delayed_correct':sum(x['correct'] for x in delayed)},flush=True)
write(ROOT/'verification/DEVELOPMENT.json',rows)
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
assert p.returncode==0 and 'Ran 116 tests' in p.stderr,p.stderr
write(ROOT/'verification/TESTS.json',{'passed':True,'tests':116,'stdout':p.stdout,'stderr':p.stderr})
freeze();print({'passed':True,'tests':116,'frozen':read(ROOT/'evaluation/FREEZE.json')['digest']},flush=True)
