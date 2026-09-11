import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
def sources():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()
        and not set(p.relative_to(ROOT).parts)&{'results','verification','examples','__pycache__'}
        and (p.suffix=='.py' or p.relative_to(ROOT).parts[0] in ('data','model') or p.name in ('PROTOCOL.json','requirements.txt'))}
def freeze():
    files=sources();digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(ROOT/'evaluation/FREEZE.json',{'files':files,'digest':digest});return digest
def verify():
    r=read(ROOT/'evaluation/FREEZE.json');assert r['files']==sources(),'frozen_source_changed';return r['digest']
def preserve():
    r=read(ROOT/'verification/PREVIOUS.json');old=ROOT.parent/r['source_release']
    assert {p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}==r['previous_files']
    assert sha(old.with_name(old.name+'.zip'))==r['previous_zip_sha256']
    for target,item in r['copied'].items():assert sha(ROOT/target)==sha(old/item['source'])==item['sha256'],target
    return {'passed':True,'previous_files':len(r['previous_files']),'copied_files':len(r['copied']),'previous_archives':1}
