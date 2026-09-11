import hashlib
import json
from pathlib import Path
from plm_l1_v09.component.algebra import canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(canonical(value) + '\n')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def sources():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()
            and '__pycache__' not in p.parts and p.relative_to(ROOT).parts[0] not in ('results', 'verification', 'examples')
            and (p.suffix == '.py' or p.relative_to(ROOT).parts[0] in ('data', 'model') or p.name in ('PROTOCOL.json', 'requirements.txt'))}


def freeze():
    files = sources()
    write(ROOT / 'evaluation/FREEZE.json', {'files': files, 'digest': digest(files)})


def verify():
    expected = read(ROOT / 'evaluation/FREEZE.json')
    actual = sources()
    assert actual == expected['files'] and digest(actual) == expected['digest'], 'frozen_sources_changed'
    return expected['digest']
