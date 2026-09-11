import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];old=BASE/'outputs/PLM-L1-SS-doc-v0.3';new=BASE/'outputs/PLM-L1-SS-doc-v0.4'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not new.exists();new.mkdir()
prior={p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}
for name in ('ss_partial','ss_document','plm_l1_v09','ss_retention','model','data'):
    shutil.copytree(old/name,new/name)
(new/'evaluation').mkdir();(new/'tests').mkdir();(new/'verification').mkdir();(new/'examples').mkdir()
for name in ('__init__.py','integrity.py','cases.py','oracle.py','event_oracle.py'):shutil.copy2(old/'evaluation'/name,new/'evaluation'/name)
shutil.copy2(old/'tests/test_retention.py',new/'tests/test_retention.py')
shutil.copy2(old/'requirements.txt',new/'requirements.txt')
record={'release':old.name,'files':prior,'zip_sha256':sha(old.with_name(old.name+'.zip')),
        'copied_files':{p.relative_to(new).as_posix():sha(p) for p in new.rglob('*') if p.is_file()}}
with (new/'verification/PREVIOUS_BASELINE.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,sort_keys=True)
print({'created':str(new),'previous_files':len(prior),'copied':len(record['copied_files'])})
