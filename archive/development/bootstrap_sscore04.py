import hashlib, json, shutil
from pathlib import Path
root=Path(__file__).resolve().parent.parent
old=root/'outputs/PLM-L1-SS-core-v0.3'
new=root/'outputs/PLM-L1-SS-core-v0.4'
new.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
copied={}
for folder in ('plm_l1_v09','ss_document','ss_partial','ss_revision','ss_retention','ss_reconfirm',
               'ss_core','ss_core_v02','ss_core_v03','bridge','vendor','model','programs','tests','data'):
    for p in sorted((old/folder).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            q=new/p.relative_to(old);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
            copied[q.relative_to(new).as_posix()]=sha(p)
for f in ('ss_core_v04','evaluation','verification'):(new/f).mkdir()
for f in ('__init__.py','integrity.py','ports.py','faults.py','oracle.py','event_oracle.py'):
    shutil.copy2(old/'evaluation'/f,new/'evaluation'/f);copied['evaluation/'+f]=sha(old/'evaluation'/f)
shutil.copy2(old/'results/MAIN.json',new/'data/V03_MAIN.json')
copied['data/V03_MAIN.json']=sha(old/'results/MAIN.json')
record={'source':old.name,'previous_files':{p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()},
        'previous_zip_sha256':sha(old.with_name(old.name+'.zip')),'copied':copied}
(new/'verification/PREVIOUS.json').write_text(json.dumps(record,ensure_ascii=False,sort_keys=True)+'\n',encoding='utf-8')
print({'new':str(new),'copied':len(copied),'previous_files':len(record['previous_files'])})
