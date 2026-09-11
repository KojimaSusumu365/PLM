import collections,json,sys,statistics
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs'/'PLM-L1-v0.9'
sys.path.insert(0,str(root))
from evaluation.integrity import sha
r=json.loads((root/'results/EVALUATION.json').read_text(encoding='utf-8'))
p=json.loads((root/'results/PERFORMANCE.json').read_text(encoding='utf-8'))
print('language',json.dumps(r['language'],ensure_ascii=False))
print('temporal',json.dumps(r['temporal'],ensure_ascii=False))
agg={}
for row in r['synthetic']:
    group=('standard' if row['train_count']==24 and row['flipped_labels']==0 else 'stress',row['method'],row['dimension'],row['selection_enabled'])
    if group not in agg: agg[group]=collections.Counter()
    c=agg[group]; c['runs']+=1; c['fallback']+=row['fallback_full_context']
    for stage in ('symbolic_projection','phase_retrieval'):
        for k,v in row[stage].items(): c[stage+'/'+k]+=v
    c['unknown_accepted']+=row['unregistered_accepted']; c['unknown_requests']+=row['unregistered_requests']
for key,value in agg.items(): print('aggregate',key,dict(value))
for method in ('ss','symbolic','id3','full'):
    rows=[x for x in p['synthetic'] if x['method']==method and x['dimension']==2048 and x['selection_enabled'] and x['task_id'].endswith('/24/0')]
    print('perf',method,{k:statistics.median(x[k] for x in rows) for k in ('selection_seconds','compile_seconds','phase_query_seconds','owned_heap_bytes')})
print('language performance',p['language'])
same=[]
for rel in ('EVALUATION.json','model/model.json','model/weights.npz','model/component/model.json','model/component/weights.npz'):
    a=root/'results'/rel; b=root.parents[1]/'work/v09-repeat'/rel
    same.append({'file':rel,'sha256':sha(a),'repeat_sha256':sha(b),'equal':sha(a)==sha(b)})
print('repeat',json.dumps(same))
print('fp',r['model_fingerprint'],r['component_fingerprint'])
for n,x in r['selection_audits']['ss'].items(): print('mask',n,x['selected_masks'],x['selected_contexts'])
