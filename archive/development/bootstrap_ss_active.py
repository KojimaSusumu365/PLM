import hashlib
import json
import shutil
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
outputs = workspace / 'outputs'; root = outputs / 'PLM-L1-SS-active-v0.1'
assert not root.exists()
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
previous = {p.relative_to(outputs).as_posix(): sha(p) for p in sorted(outputs.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}
archive = outputs / 'PLM-L1-SS-multicode-v0.1.zip'
assert sha(archive) == '66f0876a6b143bda19545a12a7a33f505b3944f403f43e79f47ddafdb4164676'
for directory in ('ss_active', 'ss_multicode', 'evaluation', 'data', 'tests', 'verification', 'vendor'):
    (root / directory).mkdir(parents=True)
copied = {}
for n in ('__init__.py', 'algebra.py', 'model.py', 'learning.py'):
    p = root / 'ss_multicode' / n
    shutil.copyfile(outputs / 'PLM-L1-SS-multicode-v0.1/ss_multicode' / n, p)
    copied[p.relative_to(root).as_posix()] = sha(p)
shutil.copyfile(archive, root / 'vendor' / archive.name)
with (root / 'verification/BASELINE.json').open('x', encoding='utf-8') as f:
    json.dump({'previous_files': previous, 'copied_core_files': copied, 'vendor_sha256': sha(archive)}, f, ensure_ascii=False, indent=2)
print(json.dumps({'previous_files': len(previous), 'copied_core_files': copied}), flush=True)
