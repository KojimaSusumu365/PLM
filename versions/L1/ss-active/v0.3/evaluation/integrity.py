import hashlib
import json
from pathlib import Path
from ss_multicode.algebra import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(canonical(value)+'\n')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()


def source_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and
                  ('__pycache__' not in p.parts) and
                  (p.suffix == '.py' and p.relative_to(ROOT).parts[0] not in ('results','verification') or
                   p.name in ('PROTOCOL.json','requirements.txt')))


def freeze():
    files = {p.relative_to(ROOT).as_posix():sha(p) for p in source_files()}
    obj = {'files': files, 'digest': digest(files), 'note': 'Before final evaluation; settings not selected from final outcomes.'}
    write(ROOT/'evaluation/FREEZE.json', obj)
    return obj


def verify_freeze():
    obj = json.loads((ROOT/'evaluation/FREEZE.json').read_text(encoding='utf-8'))
    actual = {p.relative_to(ROOT).as_posix():sha(p) for p in source_files()}
    if actual != obj['files'] or digest(actual) != obj['digest']: raise ValueError('frozen_source_changed')
    return obj['digest']
