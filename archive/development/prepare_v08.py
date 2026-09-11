"""Additive scaffold, with every pre-existing output except direction frozen."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
TARGET=OUT/'PLM-L1-v0.8'
if TARGET.exists():
    raise ValueError('fresh release required')
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
baseline={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='PLM-SS-LANGUAGE-DIRECTION.md' and '__pycache__' not in p.parts}
TARGET.mkdir()
shutil.copytree(OUT/'PLM-L1-v0.7',TARGET/'vendor'/'PLM-L1-v0.7')
shutil.copytree(OUT/'PLM-L1-v0.7'/'plm_l1_v06',TARGET/'plm_l1_v06')
for name in ('data','evaluation','tests','verification','plm_l1_v08'):
    (TARGET/name).mkdir()
shutil.copyfile(OUT/'PLM-L1-v0.7'/'data'/'folds'/'object_negative'/'train.json',TARGET/'data'/'component_train.json')
shutil.copyfile(OUT/'PLM-L1-v0.7'/'data'/'lexicon.json',TARGET/'data'/'lexicon.json')
shutil.copyfile(OUT/'PLM-L1-v0.7'/'requirements.txt',TARGET/'requirements.txt')
(TARGET/'verification'/'PRESERVED_BASELINE.json').write_text(json.dumps(baseline,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'preserved_files':len(baseline),'release':str(TARGET)}))
