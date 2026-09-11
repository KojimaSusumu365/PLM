import json,sys
from pathlib import Path
workspace=Path(__file__).resolve().parents[1]
root=workspace/'outputs/PLM-L1-v0.13'
sys.path.insert(0,str(root))
from plm_l1_v013.teaching import Session
from evaluation.cases import queries
from evaluate import snapshot,write
tasks=json.loads((root/'data/development.json').read_text(encoding='utf-8'))
tasks=[t for t in tasks if t['family'] in ('paired_simple','paired_hidden','outside_order4','roles')]
results=[]
for task in tasks:
    for retention,strategy in (('all','active'),('all','random'),('minimal','active')):
        for backend in ('ss','exact'):
            s=Session(task['initial'],task['pool'],dict(backend=backend,dimension=512,seed='development-0',retention=retention))
            snapshots=[];trace=[]
            for budget in (0,1,2,4,8,16):
                while len(s.receipts)<budget:
                    request=s.choose(strategy,'development-acquisition')
                    if request.get('status')=='no_request':break
                    label=task['teacher_answers'][request['id']]
                    trace.append({'request':request,'label':label})
                    s=s.answer(request,label)
                snapshots.append(snapshot(task,s,budget,queries(task)))
            results.append({'task_id':task['id'],'retention':retention,'strategy':strategy,'backend':backend,'trace':trace,'snapshots':snapshots})
    print(task['id'],'complete',flush=True)
out=workspace/'work/v013-critical-development.json'
write(out,results)
for r in results:
    if '/paired/' in r['task_id'] and r['backend']=='ss':
        print(r['task_id'],r['retention'],r['strategy'],[(s['budget'],s['labels_used'],s['stages'][0]['metrics']['correct'],s['stages'][0]['metrics']['wrong']) for s in r['snapshots']],flush=True)
