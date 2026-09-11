import hashlib,json,shutil
from pathlib import Path
W=Path(__file__).resolve().parent.parent;R=W/'outputs/PLM-L1-P1-S1-v0.1';R.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
records={};copied={}
for name in ('PLM-L1-SS-doc-v0.6','PLM-S1-v0.2','PLM-P1-v0.2'):
    p=W/'outputs'/name;records[name]={'files':{f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()},'zip_sha256':sha(p.with_suffix('.2.zip')) if False else sha(W/'outputs'/f'{name}.zip')}
def cp(source,dest):
    for p in sorted(source.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            q=dest/p.relative_to(source);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
            copied[q.relative_to(R).as_posix()]={'source':str(p.relative_to(W)),'sha256':sha(p)}
old=W/'outputs/PLM-L1-SS-doc-v0.6'
for package in ('plm_l1_v09','ss_document','ss_partial','ss_retention','ss_revision','ss_reconfirm','model'):
    cp(old/package,R/package)
(R/'evaluation').mkdir();(R/'data').mkdir();(R/'verification').mkdir();(R/'bridge').mkdir();(R/'tests').mkdir();(R/'examples').mkdir()
for name in ('oracle.py','event_oracle.py'):
    shutil.copy2(old/'evaluation'/name,R/'evaluation'/name);copied['evaluation/'+name]={'source':str((old/'evaluation'/name).relative_to(W)),'sha256':sha(old/'evaluation'/name)}
for name in ('lexicon.json','temporal_train.json','doc_v01_regression.json','doc_v02_scenes.json','DELAY_DATASETS.json','DELAY_EXCLUSIONS.json'):
    shutil.copy2(old/'data'/name,R/'data'/name);copied['data/'+name]={'source':str((old/'data'/name).relative_to(W)),'sha256':sha(old/'data'/name)}
s=W/'outputs/PLM-S1-v0.2';v=R/'vendor/PLM-S1-v0.2'
for folder in ('plm_s1_v02','vendor/PLM-S1-v0.1/plm_s1','vendor/PLM-S1-v0.1/vendor/PLM-P1-v0.2/plm_p1_v02','vendor/PLM-S1-v0.1/vendor/PLM-P1-v0.2/vendor/PLM-P1-v0.1/plm_p1'):
    cp(s/folder,v/folder)
(R/'verification/PREVIOUS.json').write_text(json.dumps({'previous':records,'copied':copied},ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
print({'root':str(R),'copied':len(copied),'previous_files':sum(len(x['files']) for x in records.values())})
