import hashlib,json,shutil
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];old=BASE/'outputs/PLM-L1-SS-doc-v0.4';new=BASE/'outputs/PLM-L1-SS-doc-v0.5'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not new.exists();new.mkdir()
prior={p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}
for name in ('ss_partial','ss_document','plm_l1_v09','ss_retention','ss_revision','model','data'):
    shutil.copytree(old/name,new/name)
for name in ('evaluation','tests','verification','examples'):(new/name).mkdir()
for name in ('__init__.py','integrity.py','cases.py','oracle.py','event_oracle.py','revision_cases.py','revision_experiment.py'):
    shutil.copy2(old/'evaluation'/name,new/'evaluation'/name)
for name in ('test_retention.py','test_revision.py'):shutil.copy2(old/'tests'/name,new/'tests'/name)
shutil.copy2(old/'requirements.txt',new/'requirements.txt')
record={'release':old.name,'files':prior,'zip_sha256':sha(old.with_name(old.name+'.zip')),
        'copied_files':{p.relative_to(new).as_posix():sha(p) for p in new.rglob('*') if p.is_file()}}
with (new/'verification/PREVIOUS_BASELINE.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,sort_keys=True)
print({'created':str(new),'previous_files':len(prior),'copied':len(record['copied_files'])})
