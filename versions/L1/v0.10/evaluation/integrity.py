import hashlib,json
from pathlib import Path
from .support import ROOT
from plm_l1_v010.base.component.algebra import digest

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def inventory():
    return {p.relative_to(ROOT).as_posix():sha(p) for name in ('plm_l1_v010','data','tests','evaluation') for p in sorted((ROOT/name).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.name!='SOURCE_FREEZE.json'} | {n:sha(ROOT/n) for n in ('evaluate.py','verify_release.py','requirements.txt')}

def freeze():
    files=inventory();result={'files':files,'freeze_hash':digest(files)}
    with (ROOT/'evaluation/SOURCE_FREEZE.json').open('x',encoding='utf-8') as f:f.write(json.dumps(result,indent=2)+'\n')
    return result['freeze_hash']

def verify_freeze():
    saved=json.loads((ROOT/'evaluation/SOURCE_FREEZE.json').read_text(encoding='utf-8'));files=inventory()
    if saved['files']!=files or saved['freeze_hash']!=digest(files):raise ValueError('frozen_source_changed')
    return saved['freeze_hash']

def check_manifest():
    manifest=ROOT/'RELEASE_MANIFEST.json';expected=json.loads(manifest.read_text(encoding='utf-8'))['files']
    actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    if actual!=expected:raise ValueError('release_inventory_changed')
    return len(actual)
