import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-SS-doc-v0.5';sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha
from evaluation.revision_cases import fresh
old=ROOT.parent/'PLM-L1-SS-doc-v0.4';fixtures=[];copied=set()
for cid in read(old/'results/INDEX.json')['conditions']:
    result=read(old/'results/conditions'/(cid+'.json'))
    if result['method']!='versioned_shared':continue
    cases={c['id']:c for c in read(old/f'results/DATA-{result["data_seed"]}.json')}
    for q in result['controls']['explicit_old']:
        if not q['wrong']:continue
        c=cases[q['case_id']]
        if cid not in copied:
            shutil.copytree(old/'results/memories'/cid,ROOT/'data/v04_failure_memories'/cid);copied.add(cid)
        fixtures.append({'condition':cid,'case_id':c['id'],'scope':c['scope'],'observation':fresh(c,mode='explicit_old'),
                         'truth':c['final'],'source_result_sha256':sha(old/'results/conditions'/(cid+'.json'))})
assert len(fixtures)==3
write(ROOT/'data/V04_FAILURE_FIXTURES.json',fixtures)
print({'v04_failure_fixtures':len(fixtures),'memories':len(copied)})
