"""Scaffold a new release; preserve every previous deliverable except shared history."""
import hashlib,json,shutil
from pathlib import Path
workspace=Path(__file__).resolve().parents[1]; outputs=workspace/'outputs'
old=outputs/'PLM-L1-v0.9'; new=outputs/'PLM-L1-v0.10'
assert not new.exists()
preserved={}
for p in sorted(outputs.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and p.name!='PLM-SS-LANGUAGE-DIRECTION.md':
        with p.open('rb') as f: preserved[p.relative_to(outputs).as_posix()]=hashlib.file_digest(f,'sha256').hexdigest()
for d in ('plm_l1_v010','data','tests','evaluation','verification','vendor'): (new/d).mkdir(parents=True,exist_ok=True)
shutil.copytree(old/'plm_l1_v09',new/'plm_l1_v010/base',ignore=shutil.ignore_patterns('__pycache__'))
# Mechanical namespace migration only; base runtime retains its independently
# tested v0.9 behavior. New committee logic is written in separate source files.
for p in (new/'plm_l1_v010/base').rglob('*.py'):
    s=p.read_text(encoding='utf-8').replace('plm_l1_v09','plm_l1_v010.base')
    p.write_text(s,encoding='utf-8')
for name in ('component_train','temporal_train','lexicon','single_development','single_evaluation','development','evaluation','TEMPORAL_SPLIT_AUDIT'):
    shutil.copyfile(old/'data'/(name+'.json'),new/'data'/(name+'.json'))
for name in ('oracle.py','support.py','__init__.py'):
    shutil.copyfile(old/'evaluation'/name,new/'evaluation'/name)
shutil.copyfile(old/'requirements.txt',new/'requirements.txt')
shutil.copyfile(outputs/'PLM-L1-v0.9.zip',new/'vendor/PLM-L1-v0.9.zip')
with (new/'verification/PRESERVED_BASELINE.json').open('x',encoding='utf-8') as f:
    f.write(json.dumps(preserved,ensure_ascii=False,indent=2)+'\n')
print('preserved baseline',len(preserved),'files')
