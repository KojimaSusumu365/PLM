import hashlib
import json
import shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT/'outputs/PLM-L1-SS-doc-v0.2'
NEW = ROOT/'outputs/PLM-L1-SS-doc-v0.3'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

NEW.mkdir(exist_ok=False)
for name in ('ss_partial','ss_document','plm_l1_v09','data','model'):
    shutil.copytree(OLD/name,NEW/name,ignore=shutil.ignore_patterns('__pycache__'))
for name in ('ss_retention','evaluation','verification','tests','examples'):(NEW/name).mkdir()
for name in ('oracle.py','event_oracle.py'):shutil.copy2(OLD/'evaluation'/name,NEW/'evaluation'/name)
shutil.copy2(OLD/'requirements.txt',NEW/'requirements.txt')
shutil.copy2(OLD/'results/SCENES.json',NEW/'data/doc_v02_scenes.json')
baseline={'release':OLD.name,'files':{p.relative_to(OLD).as_posix():sha(p) for p in OLD.rglob('*') if p.is_file()},
          'zip_sha256':sha(OLD.with_name(OLD.name+'.zip')),
          'copied_source':{p.relative_to(NEW).as_posix():sha(p) for package in ('ss_partial','ss_document','plm_l1_v09') for p in (NEW/package).rglob('*.py')}}
with (NEW/'verification/PREVIOUS_BASELINE.json').open('x',encoding='utf-8') as f:json.dump(baseline,f,ensure_ascii=False,sort_keys=True)
print(NEW)
