import json,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs'/'PLM-L1-v0.9'
sys.path.insert(0,str(root))
from plm_l1_v09.component.training import fit
def data(n): return json.loads((root/'data'/(n+'.json')).read_text(encoding='utf-8'))
for method in ('ss','symbolic','id3','full'):
    started=time.perf_counter()
    m=fit(data('component_train'),data('lexicon'),selector=method,seed='banked-evaluation-0')
    rows=data('single_development')
    count={'read':0,'wrong':0,'abstain':0}
    for r in rows:
        out=m.read(r['text'])
        if out['status']!='read': count['abstain']+=1
        elif m.recover(out['packet']).get('meaning')!=r['meaning']: count['wrong']+=1
        else: count['read']+=1
    print(method, count, 'seconds',time.perf_counter()-started,flush=True)
    print({n:(s['selected_masks'],s['selected_contexts'],s['fallback_full_context']) for n,s in m.selection_audit.items()},flush=True)
