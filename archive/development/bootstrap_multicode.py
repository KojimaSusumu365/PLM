import hashlib
import json
import shutil
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
outputs = workspace / 'outputs'
root = outputs / 'PLM-L1-SS-multicode-v0.1'
assert not root.exists()
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
previous = {p.relative_to(outputs).as_posix(): sha(p) for p in sorted(outputs.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}
archive = outputs / 'PLM-L1-SS-online-v0.1.zip'
assert sha(archive) == '8f6bc734ec6578fc7756168c298c87f43f3d8fb838f1f0104bd6c0b16a1c3c1a'
for directory in ('ss_multicode', 'evaluation', 'data', 'tests', 'verification', 'vendor'):
    (root / directory).mkdir(parents=True)
shutil.copyfile(archive, root / 'vendor' / archive.name)
shutil.copyfile(outputs / 'PLM-L1-SS-online-v0.1/ss_online/algebra.py', root / 'ss_multicode/algebra.py')
shutil.copyfile(outputs / 'PLM-L1-SS-online-v0.1/evaluation/cases.py', root / 'evaluation/cases.py')
with (root / 'verification/BASELINE.json').open('x', encoding='utf-8') as f:
    json.dump({'previous_files': previous,
               'copied_algebra_sha256': sha(root / 'ss_multicode/algebra.py'),
               'vendor_sha256': sha(archive)}, f, ensure_ascii=False, indent=2)
print(json.dumps({'preserved_files': len(previous), 'root': str(root)}), flush=True)
