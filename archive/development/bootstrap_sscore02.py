import hashlib,json,shutil
from pathlib import Path
W=Path(__file__).resolve().parent.parent
O=W/'outputs/PLM-L1-SS-core-v0.1'
R=W/'outputs/PLM-L1-SS-core-v0.2'
R.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
copied={}
for package in ('plm_l1_v09','ss_document','ss_partial','ss_retention','ss_revision','ss_reconfirm','bridge','vendor','model','ss_core','data','tests'):
    for p in sorted((O/package).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':
            q=R/p.relative_to(O);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
            copied[q.relative_to(R).as_posix()]={'source':p.relative_to(O).as_posix(),'sha256':sha(p)}
for folder in ('ss_core_v02','evaluation','verification','examples'):(R/folder).mkdir()
for name in ('oracle.py','event_oracle.py','channel.py','ports.py','prior_cases.py','prior_experiment.py','cases.py','experiment.py'):
    dest='core01_experiment.py' if name=='experiment.py' else name
    shutil.copy2(O/'evaluation'/name,R/'evaluation'/dest)
    copied['evaluation/'+dest]={'source':'evaluation/'+name,'sha256':sha(O/'evaluation'/name)}
for seed in range(3):
    for p in (O/f'results/runs/{seed}-stream1/memory').rglob('*'):
        if p.is_file():
            q=R/'data/CORE01_MEMORIES'/str(seed)/p.relative_to(O/f'results/runs/{seed}-stream1/memory')
            q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
            copied[q.relative_to(R).as_posix()]={'source':p.relative_to(O).as_posix(),'sha256':sha(p)}
for old,new in [('results/UPDATE_FAULTS.json','data/CORE01_UPDATE_FAULTS.json'),('results/ROWS.json','data/CORE01_ROWS.json')]:
    shutil.copy2(O/old,R/new);copied[new]={'source':old,'sha256':sha(O/old)}
record={'source_release':O.name,'previous_files':{p.relative_to(O).as_posix():sha(p) for p in O.rglob('*') if p.is_file()},
        'previous_zip_sha256':sha(O.with_name(O.name+'.zip')),'copied':copied}
(R/'verification/PREVIOUS.json').write_text(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
print({'copied':len(copied),'previous_files':len(record['previous_files'])})
