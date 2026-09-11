import sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent/'outputs/PLM-L1-P1-S1-v0.1';sys.path.insert(0,str(R))
from evaluation.cases import build
from evaluation.integrity import write
d=build();write(R/'data/CORPUS.json',d);print({'new_scenes':d['unique_new_scenes'],'excluded':d['prior_excluded_scenes']})
