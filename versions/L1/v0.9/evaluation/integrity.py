import hashlib
import json
from pathlib import Path
from .support import ROOT
from plm_l1_v09.component.algebra import digest

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def frozen_files():
    return {p.relative_to(ROOT).as_posix():sha(p) for name in ('plm_l1_v09','evaluation','tests','data')
            for p in sorted((ROOT/name).rglob('*')) if p.is_file() and '__pycache__' not in p.parts
            and p.name!='SOURCE_FREEZE.json'} | {name:sha(ROOT/name) for name in ('evaluate.py','verify_release.py','requirements.txt')}

def freeze():
    rows=frozen_files(); result={'files':rows,'freeze_hash':digest(rows)}
    with (ROOT/'evaluation'/'SOURCE_FREEZE.json').open('x',encoding='utf-8') as f:
        f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result['freeze_hash']

def verify_freeze():
    saved=json.loads((ROOT/'evaluation'/'SOURCE_FREEZE.json').read_text(encoding='utf-8'))
    actual=frozen_files()
    if actual!=saved['files'] or digest(actual)!=saved['freeze_hash']: raise ValueError('frozen_source_changed')
    return saved['freeze_hash']

def manifest_check():
    manifest=ROOT/'RELEASE_MANIFEST.json'
    expected=json.loads(manifest.read_text(encoding='utf-8'))['files']
    actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    if actual!=expected: raise ValueError('release_inventory_or_hash_mismatch')
    return len(actual)
