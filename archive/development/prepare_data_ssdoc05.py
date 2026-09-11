import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-SS-doc-v0.5';sys.path.insert(0,str(ROOT))
from plm_l1_v09.component.algebra import digest
from evaluation.integrity import read,write
from evaluation.cases import scene_key
from evaluation.reconfirm_cases import build,audit_datasets,footprint
from ss_partial.contract import to_meaning
lex=read(ROOT/'data/lexicon.json')['slot_candidates'];exclude=set()
for name in ('temporal_train.json','doc_v01_regression.json','doc_v02_scenes.json'):
    exclude.update(digest(scene_key(r['meaning'])) for r in read(ROOT/'data'/name))
prior=ROOT.parent/'PLM-L1-SS-doc-v0.4'
for seed in (200,201):
    for c in read(prior/f'results/DATA-{seed}.json'):exclude.update(footprint(c,lex))
write(ROOT/'data/SPLIT_EXCLUSIONS.json',sorted(exclude));data=build(exclude);audit=audit_datasets(data,exclude)
write(ROOT/'data/RECONFIRM_DATASETS.json',data);write(ROOT/'verification/DATA_AUDIT.json',audit)
print({'passed':True,'construction':data['construction_audit'],'audit':audit},flush=True)
