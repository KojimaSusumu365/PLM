"""Content freeze includes code, fixed teachers, models, program and numeric bundle."""
import argparse,hashlib,json
from pathlib import Path
from .integrity import sha,read,write
ROOT=Path(__file__).resolve().parents[1]

def sources():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()
            and not set(p.relative_to(ROOT).parts)&{'results','verification','__pycache__'}
            and (p.suffix=='.py' or p.relative_to(ROOT).parts[0] in ('data','model','programs','bundle04') or p.name in ('PROTOCOL.json','requirements.txt'))}

def freeze():
    files=sources();digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(ROOT/'verification/FREEZE04.json',{'files':files,'digest':digest});return digest

def verify():
    r=read(ROOT/'verification/FREEZE04.json');assert r['files']==sources(),'frozen_source_changed';return r['digest']

def preserve():
    r=read(ROOT/'verification/PREVIOUS.json');old=ROOT.parent/r['source']
    assert {p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}==r['previous_files']
    assert sha(old.with_name(old.name+'.zip'))==r['previous_zip_sha256']
    for target,item in r['copied'].items():
        expected=item['sha256'] if isinstance(item,dict) else item
        assert sha(ROOT/target)==expected,target
    return {'previous_files':len(r['previous_files']),'copied_files':len(r['copied']),'previous_zip_unchanged':True}

def manifest():
    target=ROOT/'verification/MANIFEST04.json'
    files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and p!=target and '__pycache__' not in p.parts}
    write(target,{'files':files});return len(files)

def check_manifest():
    r=read(ROOT/'verification/MANIFEST04.json');actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='MANIFEST04.json' and '__pycache__' not in p.parts}
    assert actual==r['files'],'manifest_mismatch';return len(actual)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('freeze','verify','preserve','manifest','check-manifest'));a=p.parse_args()
    print({'result':{'freeze':freeze,'verify':verify,'preserve':preserve,'manifest':manifest,'check-manifest':check_manifest}[a.mode]()})
