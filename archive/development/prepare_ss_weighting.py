"""Create a fresh experiment tree; copy original files without modifying them."""
import hashlib
import json
import shutil
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
outputs = workspace / 'outputs'
base = outputs / 'PLM-L1-v0.13'
target = outputs / 'PLM-L1-SS-weighting-v0.1'
target.mkdir(exist_ok=False)
for name in ('ss_weighting', 'tests', 'evaluation', 'data', 'verification', 'vendor'):
    (target / name).mkdir()
shutil.copytree(base / 'plm_l1_v013', target / 'plm_l1_v013', ignore=shutil.ignore_patterns('__pycache__'))
shutil.copyfile(base / 'data/evaluation.json', target / 'data/v013-evaluation.json')
shutil.copyfile(base / 'evaluation/cases.py', target / 'evaluation/legacy_cases.py')
shutil.copyfile(base / 'evaluation/legacy_tasks.py', target / 'evaluation/legacy_tasks.py')
shutil.copyfile(base / 'tests/test_v013.py', target / 'tests/test_v013.py')
shutil.copyfile(outputs / 'PLM-L1-v0.13.zip', target / 'vendor/PLM-L1-v0.13.zip')
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
preserved = {p.relative_to(outputs).as_posix(): sha(p) for p in sorted(outputs.rglob('*'))
             if p.is_file() and not p.is_relative_to(target) and '__pycache__' not in p.parts}
copied = {p.relative_to(target).as_posix(): sha(p) for p in sorted(target.rglob('*')) if p.is_file()}
with (target / 'verification/BASELINE.json').open('x', encoding='utf-8') as f:
    json.dump({'previous_files': preserved, 'copied_files': copied}, f, indent=2)
print(json.dumps({'root': str(target), 'previous_files': len(preserved), 'copied': len(copied)}))
