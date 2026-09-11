"""Final development-only diagnostics and record preservation before freeze."""
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'outputs'/'PLM-L1-v0.8'
sys.path.insert(0,str(RELEASE))
from evaluation_support import data
from measurements import noise_probe,noise_rng
from evaluate import judge
from plm_l1_v08.runtime import TemporalModel
import numpy as np

initial=ROOT/'work'/'v08-development-01'
for name in ('EVALUATION.json','REPORT.md'):
    shutil.copyfile(initial/name,RELEASE/'verification'/('DEVELOPMENT_01_'+name))
shutil.copyfile(ROOT/'work'/'v08-boundary-preflight'/'VERIFICATION.json',RELEASE/'verification'/'BOUNDARY_PREFLIGHT.json')
assert not np.array_equal(noise_rng('temporal-noise-development-0').normal(size=32),noise_rng('temporal-noise-development-1').normal(size=32))
result=json.loads((initial/'EVALUATION.json').read_text(encoding='utf-8'))
protocol=json.loads((RELEASE/'evaluation'/'PROTOCOL.json').read_text(encoding='utf-8'))
# Development counterpart of all formal gates, with its own seed inventory.
dev=dict(protocol,evaluation_seeds=protocol['development_seeds'],noise_seeds=['temporal-noise-0','temporal-noise-1'])
checks=judge(result,dev)
assert all(c['passed'] for c in checks),[c for c in checks if not c['passed']]
rows=data('development'); candidates=data('lexicon')['slot_candidates']; diagnostics=[]
for dimension in (128,8192):
    for level in protocol['noise_levels']:
        diagnostics.append(noise_probe(candidates,rows,dimension,'temporal-noise-development-0',level))
record={'status':'development_checks_passed_not_frozen_evaluation','development_gate_count':len(checks),
        'development_gates':checks,'noise_rng_suffix_changes_direction':True,'noise_diagnostics':diagnostics}
with (RELEASE/'verification'/'FINAL_DEVELOPMENT.json').open('x',encoding='utf-8') as f: json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'status':record['status'],'development_gates':len(checks),'noise':[{k:r[k] for k in ('dimension','level','counts')} for r in diagnostics]},ensure_ascii=False))
