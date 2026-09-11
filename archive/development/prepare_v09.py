"""Additive v0.9 scaffold; preserve every pre-existing deliverable except history."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
NEW = OUT / 'PLM-L1-v0.9'
OLD = OUT / 'PLM-L1-v0.8'
assert not NEW.exists()

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

baseline = {p.relative_to(OUT).as_posix(): sha(p) for p in sorted(OUT.rglob('*'))
            if p.is_file() and p.name != 'PLM-SS-LANGUAGE-DIRECTION.md' and '__pycache__' not in p.parts}
NEW.mkdir()
for name in ('data', 'tests', 'evaluation', 'verification', 'vendor', 'plm_l1_v09'):
    (NEW / name).mkdir()
# Keep original v0.8 as an intact archive, avoiding an extra nested Windows path.
shutil.copyfile(OUT / 'PLM-L1-v0.8.zip', NEW / 'vendor' / 'PLM-L1-v0.8.zip')
shutil.copytree(OLD / 'plm_l1_v06', NEW / 'plm_l1_v09' / 'component')
for p in (OLD / 'plm_l1_v08').glob('*.py'):
    shutil.copyfile(p, NEW / 'plm_l1_v09' / p.name)
for name in ('component_train.json', 'lexicon.json', 'temporal_train.json', 'development.json', 'evaluation.json', 'TEMPORAL_SPLIT_AUDIT.json'):
    shutil.copyfile(OLD / 'data' / name, NEW / 'data' / name)
for name in ('train', 'development', 'evaluation'):
    origin = OLD / 'vendor' / 'PLM-L1-v0.7' / 'data' / (name + '.json')
    if origin.exists():
        shutil.copyfile(origin, NEW / 'data' / ('single_' + name + '.json'))
shutil.copyfile(OLD / 'requirements.txt', NEW / 'requirements.txt')
with (NEW / 'verification' / 'PRESERVED_BASELINE.json').open('x', encoding='utf-8') as f:
    json.dump(baseline, f, indent=2)
print(json.dumps({'preserved_files': len(baseline), 'v08_archive_sha256': sha(NEW/'vendor'/'PLM-L1-v0.8.zip')}))
