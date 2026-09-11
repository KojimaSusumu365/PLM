import hashlib
import json
from pathlib import Path
from plm_l1_v011.algebra import digest

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def inventory():
    return {p.relative_to(ROOT).as_posix(): sha(p)
            for folder in ('plm_l1_v011', 'plm_l1_v012', 'evaluation', 'tests', 'data')
            for p in sorted((ROOT / folder).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.name != 'SOURCE_FREEZE.json'} | {
                n: sha(ROOT / n) for n in ('requirements.txt', 'evaluate.py', 'verify_release.py')}


def freeze():
    files = inventory()
    record = {'files': files, 'freeze_hash': digest(files)}
    with (ROOT / 'evaluation/SOURCE_FREEZE.json').open('x', encoding='utf-8') as f:
        f.write(json.dumps(record, indent=2) + '\n')
    return record['freeze_hash']


def verify_freeze():
    record = json.loads((ROOT / 'evaluation/SOURCE_FREEZE.json').read_text(encoding='utf-8'))
    files = inventory()
    if files != record['files'] or digest(files) != record['freeze_hash']:
        raise ValueError('source_freeze_mismatch')
    return record['freeze_hash']


def manifest():
    expected = json.loads((ROOT / 'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files']
    actual = {p.relative_to(ROOT).as_posix(): sha(p) for p in ROOT.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'RELEASE_MANIFEST.json'}
    if actual != expected:
        raise ValueError('release_inventory_mismatch')
    return len(actual)
