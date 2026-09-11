import hashlib
import json
from pathlib import Path
from ss_multicode.algebra import digest
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False); f.write('\n')


def inventory():
    files = {p.relative_to(ROOT).as_posix(): sha(p) for folder in ('ss_multicode', 'evaluation', 'data', 'tests')
             for p in sorted((ROOT / folder).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name != 'FREEZE.json'}
    return files | {n: sha(ROOT / n) for n in ('evaluate.py', 'calibrate.py', 'verify_release.py', 'requirements.txt')}


def freeze():
    files = inventory(); h = digest(files); write(ROOT / 'evaluation/FREEZE.json', {'files': files, 'freeze_hash': h}); return h


def verify():
    old = json.loads((ROOT / 'evaluation/FREEZE.json').read_text(encoding='utf-8')); files = inventory()
    if old['files'] != files or old['freeze_hash'] != digest(files): raise ValueError('freeze_mismatch')
    return digest(files)
