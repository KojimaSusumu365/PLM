import sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];ROOT=BASE/'outputs/PLM-L1-SS-doc-v0.6';sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write
from evaluation.reconfirm_cases import footprint
from evaluation.delay_cases import build,audit
exclusions=set(read(ROOT/'data/SPLIT_EXCLUSIONS.json'));lex=read(ROOT/'data/lexicon.json')['slot_candidates']
for ds in read(ROOT/'data/RECONFIRM_DATASETS.json')['splits'].values():
    for c in ds['cases']:exclusions.update(footprint(c,lex))
write(ROOT/'data/DELAY_EXCLUSIONS.json',sorted(exclusions));data=build(exclusions);write(ROOT/'data/DELAY_DATASETS.json',data)
record=audit(read(ROOT/'data/DELAY_DATASETS.json'),exclusions);write(ROOT/'verification/DATA_AUDIT.json',record)
print(record)
