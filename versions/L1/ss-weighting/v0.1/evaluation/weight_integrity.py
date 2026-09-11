import hashlib
import json
from pathlib import Path
from plm_l1_v013.algebra import digest
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, obj):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def inventory():
    included = ('ss_weighting', 'plm_l1_v013', 'evaluation', 'tests', 'data')
    files = {p.relative_to(ROOT).as_posix(): sha(p) for d in included for p in sorted((ROOT/d).rglob('*'))
             if p.is_file() and '__pycache__' not in p.parts and p.name != 'WEIGHT_FREEZE.json'}
    return files | {n: sha(ROOT/n) for n in ('evaluate_weights.py', 'verify_release.py', 'requirements.txt')}


def freeze():
    files = inventory()
    write(ROOT/'evaluation/WEIGHT_FREEZE.json', {'files': files, 'freeze_hash': digest(files)})
    return digest(files)


def verify():
    saved = json.loads((ROOT/'evaluation/WEIGHT_FREEZE.json').read_text(encoding='utf-8'))
    files = inventory()
    if saved['files'] != files or saved['freeze_hash'] != digest(files):
        raise ValueError('freeze_mismatch')
    return digest(files)
