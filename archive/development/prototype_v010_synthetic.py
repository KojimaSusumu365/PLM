import sys,collections
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-v0.10'; sys.path.insert(0,str(root))
from evaluation.support import data
from evaluation.synthetic import run
for t in data('ambiguity_development'):
    for method in ('ss_multi','ss_single','symbolic_multi','v09_single'):
        for after in (False,True):
            r,p=run(t,method,2048,'candidate-development-0',after=after)
            print(t['id'],method,after,r['audit']['selected_masks'],r['ungated'],r['calibrated'],flush=True)
for t in data('dependencies_development'):
    if t['replicate'] or t['train_count']!=24: continue
    r,p=run(t,'ss_multi',2048,'candidate-development-0')
    print(t['id'],r['audit']['selected_masks'],r['ungated'],r['calibrated'],flush=True)
