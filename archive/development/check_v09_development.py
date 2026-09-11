import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'/'PLM-L1-v0.9'))
from evaluation.support import data,six_pairs
from evaluation.synthetic import run
from plm_l1_v09.component.training import fit
from evaluate import single
start=time.perf_counter()
for task in data('dependencies_development'):
    if task['train_count']==24 and task['flipped_labels']==0:
        for method in ('ss','symbolic','id3','full'):
            r,p=run(task,method,2048,'selection-development-0')
            print(task['id'],method,r['selected_masks'],r['symbolic_projection'],r['phase_retrieval'],flush=True)
m=fit(six_pairs(),data('lexicon'),selector='ss',selection_seed='selection-development-0',seed='banked-evaluation-0')
print('six',single(m,data('single_development')),flush=True)
print('elapsed',time.perf_counter()-start,flush=True)
