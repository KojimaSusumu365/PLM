import hashlib,json
from pathlib import Path
from ss_multicode.algebra import digest
ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write(path,obj):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')


def inventory(development=False):
    excluded={'FREEZE.json','DEVELOPMENT_INPUTS.json'}|({'SELECTED.json'} if development else set())
    files={p.relative_to(ROOT).as_posix():sha(p) for d in ('ss_multicode','ss_active','evaluation','data','tests') for p in sorted((ROOT/d).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in excluded}
    names=('evaluate.py','requirements.txt') if development else ('evaluate.py','verify_release.py','requirements.txt')
    return files|{n:sha(ROOT/n) for n in names}


def lock_development():
    f=inventory(True);write(ROOT/'evaluation/DEVELOPMENT_INPUTS.json',{'files':f,'digest':digest(f)})


def verify_development():
    f=inventory(True);old=json.loads((ROOT/'evaluation/DEVELOPMENT_INPUTS.json').read_text(encoding='utf-8'))
    if f!=old['files'] or digest(f)!=old['digest']:raise ValueError('development_inputs_changed')
    return digest(f)


def freeze():
    verify_development();f=inventory();write(ROOT/'evaluation/FREEZE.json',{'files':f,'freeze_hash':digest(f)});return digest(f)


def verify():
    verify_development();f=inventory();old=json.loads((ROOT/'evaluation/FREEZE.json').read_text(encoding='utf-8'))
    if f!=old['files'] or digest(f)!=old['freeze_hash']:raise ValueError('freeze_mismatch')
    return digest(f)
