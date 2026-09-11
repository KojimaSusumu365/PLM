import hashlib,json,shutil
from pathlib import Path
W=Path(__file__).resolve().parent.parent;O=W/'outputs/PLM-L1-P1-S1-v0.1';R=W/'outputs/PLM-L1-SS-core-v0.1';R.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
copied={}
for package in ('plm_l1_v09','ss_document','ss_partial','ss_retention','ss_revision','ss_reconfirm','bridge','vendor','model'):
    for p in sorted((O/package).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            q=R/p.relative_to(O);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);copied[q.relative_to(R).as_posix()]=sha(p)
for folder in ('ss_core','evaluation','data','tests','verification','examples'):(R/folder).mkdir()
for name in ('lexicon.json','temporal_train.json','doc_v01_regression.json','doc_v02_scenes.json','DELAY_DATASETS.json','DELAY_EXCLUSIONS.json'):
    shutil.copy2(O/'data'/name,R/'data'/name);copied['data/'+name]=sha(O/'data'/name)
shutil.copy2(O/'data/CORPUS.json',R/'data/BRIDGE_CORPUS.json')
for name in ('oracle.py','event_oracle.py'):
    shutil.copy2(O/'evaluation'/name,R/'evaluation'/name);copied['evaluation/'+name]=sha(O/'evaluation'/name)
record={'source_release':O.name,'previous_files':{p.relative_to(O).as_posix():sha(p) for p in O.rglob('*') if p.is_file()},
        'previous_zip_sha256':sha(O.with_name(O.name+'.zip')),'copied':copied}
(R/'verification/PREVIOUS.json').write_text(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
print({'root':str(R),'copied':len(copied),'previous_files':len(record['previous_files'])})
