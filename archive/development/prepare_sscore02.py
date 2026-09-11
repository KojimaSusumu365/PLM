import sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent/'outputs/PLM-L1-SS-core-v0.2';sys.path.insert(0,str(R))
from evaluation.integrity import write
from evaluation.guard_cases import build
r=build();write(R/'data/GUARD_CORPUS.json',r)
print({k:v for k,v in r.items() if k!='splits'})
