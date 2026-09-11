import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:f.write(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
def sources():
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and
        not set(p.relative_to(ROOT).parts)&{'verification','results','examples'} and
        (p.suffix=='.py' or p.relative_to(ROOT).parts[0] in ('data','model') or p.name in ('PROTOCOL.json','requirements.txt'))}
def freeze():
    h=sources();d=hashlib.sha256(json.dumps(h,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write(ROOT/'evaluation/FREEZE.json',{'files':h,'digest':d});return d
def verify():
    f=read(ROOT/'evaluation/FREEZE.json');assert sources()==f['files'],'frozen_source_changed';return f['digest']
def preserve():
    record=read(ROOT/'verification/PREVIOUS.json');work=ROOT.parents[1]
    for name,r in record['previous'].items():
        p=ROOT.parent/name;assert {f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()}==r['files']
        assert sha(ROOT.parent/f'{name}.zip')==r['zip_sha256']
    for name,r in record['copied'].items():assert sha(ROOT/name)==r['sha256'] and sha(work/r['source'])==r['sha256']
    return {'passed':True,'previous_files':sum(len(x['files']) for x in record['previous'].values()),'copied_files':len(record['copied']),'previous_archives':3}
