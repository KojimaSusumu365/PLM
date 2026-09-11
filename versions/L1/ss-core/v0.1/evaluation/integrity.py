import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False)+'\n')

def sources():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()
            and not set(p.relative_to(ROOT).parts)&{'verification','results','examples','__pycache__'}
            and (p.suffix=='.py' or p.relative_to(ROOT).parts[0] in ('data','model')
                 or p.name in ('PROTOCOL.json','requirements.txt'))}

def freeze():
    files = sources()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',',':')).encode()).hexdigest()
    write(ROOT/'evaluation/FREEZE.json', {'files':files,'digest':digest})
    return digest

def verify():
    record = read(ROOT/'evaluation/FREEZE.json')
    assert record['files'] == sources(), 'frozen_source_changed'
    return record['digest']

def preserve():
    r = read(ROOT/'verification/PREVIOUS.json')
    old = ROOT.parent/r['source_release']
    assert {p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()} == r['previous_files']
    assert sha(old.with_name(old.name+'.zip')) == r['previous_zip_sha256']
    for path, expected in r['copied'].items():
        assert sha(ROOT/path) == expected and sha(old/path) == expected, path
    assert sha(ROOT/'data/BRIDGE_CORPUS.json') == sha(old/'data/CORPUS.json')
    for name, original in [('prior_cases.py','cases.py'), ('prior_experiment.py','experiment.py'), ('channel.py','channel.py')]:
        assert sha(ROOT/'evaluation'/name) == sha(old/'evaluation'/original)
    return {'passed':True,'previous_files':len(r['previous_files']), 'copied_files':len(r['copied'])+4, 'previous_archives':1}
