import sys
from pathlib import Path
R = Path(__file__).resolve().parent.parent/'outputs/PLM-L1-SS-core-v0.1'
sys.path.insert(0,str(R))
from evaluation.cases import build
from evaluation.integrity import write
data = build()
write(R/'data/CORPUS.json',data)
print({'new_scenes':data['unique_new_scenes'],'excluded':data['prior_excluded_scenes']})
