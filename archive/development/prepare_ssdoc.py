import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];release=root/'outputs/PLM-L1-SS-doc-v0.1';sys.path.insert(0,str(release))
from evaluation.integrity import read,write,sha,freeze
from ss_document.training import train
from plm_l1_v09.runtime import TemporalModel
from evaluation.cases import corpus
from evaluation.experiment import trial

model=train(read(release/'data/component_train.json'),read(release/'data/temporal_train.json'),read(release/'data/lexicon.json'))
original=TemporalModel.load(root/'outputs/PLM-L1-v0.9/results/model')
assert model.base.fingerprint==original.fingerprint
checks=[]
for case in corpus('development',4):
    row,_=trial(model,case,False);checks.append(row)
write(release/'verification/DEVELOPMENT.json',{'rows':checks,'base_refit_matches_v09':True,
      'note':'Separate48 development inputs. No setting search or final-data tuning.'})
baselines={}
for name in ('PLM-L1-v0.9','PLM-L1-SS-active-v0.3'):
    p=root/'outputs'/name
    baselines[name]={'files':{f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()},
                     'zip_sha256':sha(root/'outputs'/(name+'.zip'))}
for p in (release/'plm_l1_v09').rglob('*.py'):
    assert sha(p)==sha(root/'outputs/PLM-L1-v0.9/plm_l1_v09'/p.relative_to(release/'plm_l1_v09'))
write(release/'verification/PREVIOUS_BASELINE.json',baselines)
print(json.dumps({'development_inputs':len(checks),'read_correct':sum(r['read_semantic_equal'] for r in checks),
                 'connected_correct':sum(r['outputs'][0]['score'] is not None and r['outputs'][0]['score']['semantic_equal'] for r in checks),
                 'base_refit_matches_v09':True,'freeze':freeze()['digest']},indent=2))
