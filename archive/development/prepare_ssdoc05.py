import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-SS-doc-v0.5';sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,freeze
from evaluation.revision_cases import prepared_data
from evaluation.reconfirm_experiment import episode,probe,failure_regression
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_revision.learning import learn

model=PartialModel.load(ROOT/'model');ds=read(ROOT/'data/RECONFIRM_DATASETS.json')['splits']['development'];data=ds['cases'];records=prepared_data(model,data);rows=[]
for method in ('versioned_shared','versioned_pair'):
    for policy in ('legacy','always','ss_selective'):
        m=RevisionMemory(model.codec.candidates,method,'reconfirmation-development')
        for r in records:m.register(r['root'],r['targets'],r['kind']=='focal')
        for step in range(5):
            for r in records[:6]:learn(m,r['teachers'][step]['prepared'])
        for step in range(2):
            for r in records[6:]:learn(m,r['teachers'][step]['prepared'])
        used=0;episodes=[]
        for i in ds['query_order']:
            r=episode(model,m,data[i],policy,6-used);used+=r['confirmations_used'];episodes.append(r)
        cold=[probe(model,m,data[i])[0] for i in ds['query_order']]
        rows.append({'method':method,'policy':policy,'budget_cap':6,'used':used,'primary':episodes,'cold':cold})
        print({'method':method,'policy':policy,'used':used,'correct':sum(r['final']['correct'] for r in episodes)},flush=True)
write(ROOT/'verification/DEVELOPMENT.json',{'rows':rows,'note':'36 development episodes and36 cold probes;budget6 per six-episode stream;not primary data.'})
regression=failure_regression(model);write(ROOT/'verification/DEVELOPMENT_REGRESSION.json',regression)
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
write(ROOT/'verification/TESTS.json',{'passed':True,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
freeze();print({'passed':True,'tests':86,'frozen':True},flush=True)
