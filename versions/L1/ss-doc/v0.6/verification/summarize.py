import sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write

def semantic(rows):
    return {'episodes':len(rows),'correct':sum(r['correct'] for r in rows),'wrong':sum(r['wrong'] for r in rows),
            'held':sum(not(r['correct'] or r['wrong']) for r in rows)}

def document(rows):
    g=[o for r in rows for o in r['outputs'] if o['generation']['status']=='generated']
    return {**semantic(rows),'requested_outputs':len(rows)*2,'generated_outputs':len(g),
       'generated_documents':sum(len(r['outputs'])==2 and all(o['generation']['status']=='generated' for o in r['outputs']) for r in rows),
       'correct_text_documents':sum(len(r['outputs'])==2 and all(o['generation']['status']=='generated' and o['score']['semantic_equal'] for o in r['outputs']) for r in rows),
       'correct_outputs':sum(o['score']['semantic_equal'] for o in g),'wrong_outputs':sum(not o['score']['semantic_equal'] for o in g),
       'surface_valid':sum(o['score']['surface_valid'] for o in g),'goals_equal':sum(o['score']['goals_equal'] for o in g),
       'reread_equal':sum(o['reread_equal'] for o in g),'nonmutable_changed':sum(r['nonmutable_changed'] for r in rows),
       'known_changed_by_ss':sum(r['known_changed_by_ss'] for r in rows)}

def run():
    index=read(ROOT/'results/INDEX.json');groups=defaultdict(list);bybase=defaultdict(dict);failures=[]
    for cid in index['conditions']:
        r=read(ROOT/'results/conditions'/(cid+'.json'));groups[(r['method'],r['policy'],r['load'])].append(r);bybase[r['base']][r['policy']]=r
        for i,row in enumerate(r['delayed']):
            if row['wrong']:failures.append({'condition':cid,'index':i,'case_id':row['case_id'],'result':row})
    summary=[]
    for (method,policy,load),rs in sorted(groups.items()):
        before=[x for r in rs for x in read(ROOT/'results/baselines'/(r['base']+'.json'))['before']]
        base_delay=[x for r in rs for x in read(ROOT/'results/baselines'/(r['base']+'.json'))['delayed']]
        immediate=[x for r in rs for x in r['immediate']];delayed=[x for r in rs for x in r['delayed']]
        summary.append({'method':method,'policy':policy,'background_before':load,'background_after':load+64,
           'streams':len(rs),'actual_confirmations':sum(r['actual_confirmations'] for r in rs),
           'required_confirmations':sum(r['required_confirmations'] for r in rs),
           'optional_confirmations':sum(r['actual_confirmations']-r['required_confirmations'] for r in rs),
           'baseline_before':semantic(before),'baseline_delayed':semantic(base_delay),'immediate':semantic(immediate),'delayed':document(delayed),
           'lost_after_delay':sum(a['correct'] and not b['correct'] for a,b in zip(immediate,delayed)),
           'recovered_after_delay':sum(not a['correct'] and b['correct'] for a,b in zip(immediate,delayed)),
           'candidate_scores':sum(t['selection']['candidates_scored'] for r in rs for t in r['trace']),
           'by_seed':{s:document([x for r in rs if r['code']==s for x in r['delayed']]) for s in sorted({r['code'] for r in rs})}})
    paired=[];changes=[]
    for bid,policies in sorted(bybase.items()):
        learned=policies['ss_learned']
        for comparator in ('rule','random'):
            other=policies[comparator];a=learned['delayed'];b=other['delayed']
            paired.append({'base':bid,'method':learned['method'],'load':learned['load'],'comparator':comparator,
                'learned_correct':sum(x['correct'] for x in a),'comparator_correct':sum(x['correct'] for x in b),
                'learned_only_correct':sum(x['correct'] and not y['correct'] for x,y in zip(a,b)),
                'comparator_only_correct':sum(y['correct'] and not x['correct'] for x,y in zip(a,b)),
                'learned_wrong':sum(x['wrong'] for x in a),'comparator_wrong':sum(x['wrong'] for x in b),
                'equal_actual_teacher_count':learned['actual_confirmations']==other['actual_confirmations']==6})
            for i,(x,y) in enumerate(zip(a,b)):
                if x['correct']!=y['correct']:
                    changes.append({'base':bid,'comparator':comparator,'case_id':x['case_id'],
                       'learned_correct':x['correct'],'comparator_correct':y['correct'],'learned_status':x['status'],
                       'learned_immediate_correct':learned['immediate'][i]['correct'],
                       'learned_pending_targets':x['pending_targets'],
                       'learned_pending_reasons':[d['reason'] for d in x['completion'].get('decisions',[]) if d['reason']],
                       'confirmations_to_this_document':[t for t in learned['trace'] if t['selection']['question']['id']==x['case_id']]})
    result={'groups':summary,'paired':paired,'delayed_wrong_episodes':len(failures),'independent_evaluation_focal_scenes':24,
            'evaluation_code_seeds':3,'eligible_for_inference':False}
    write(ROOT/'verification/SUMMARY.json',result);write(ROOT/'verification/FAILURES.json',failures);write(ROOT/'verification/RETENTION_CHANGES.json',changes)
    for g in summary:print({k:g[k] for k in ('method','policy','background_before','actual_confirmations','delayed')})
    return result

if __name__=='__main__':run()
