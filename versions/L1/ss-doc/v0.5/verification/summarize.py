import json,sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write

def metrics(rows):
    outputs=[o for r in rows for o in r['outputs']]
    generated=[o for o in outputs if o['generation']['status']=='generated']
    return {'episodes':len(rows),'correct':sum(r['correct'] for r in rows),'wrong':sum(r['wrong'] for r in rows),
            'held':sum(not(r['correct'] or r['wrong']) for r in rows),
            'pending_targets':sum(len(r['pending_targets']) for r in rows),
            'nonmutable_changed':sum(r['nonmutable_changed'] for r in rows),'known_changed_by_ss':sum(r['known_changed_by_ss'] for r in rows),
            'requested_outputs':len(rows)*2,'generated_outputs':len(generated),
            'correct_outputs':sum(bool(o['score'] and o['score']['semantic_equal']) for o in generated),
            'wrong_outputs':sum(not bool(o['score'] and o['score']['semantic_equal']) for o in generated),
            'reread_equal':sum(o['reread_equal'] for o in generated)}

def run():
    index=read(ROOT/'results/INDEX.json');groups=defaultdict(list);failures=[]
    for cid in index['conditions']:
        r=read(ROOT/'results/conditions'/(cid+'.json'));groups[(r['method'],r['policy'],r['budget_cap'])].append(r)
        for kind,rows in [('primary',[x['final'] for x in r['primary']]),('cold',r['cold'])]:
            for i,row in enumerate(rows):
                if row['wrong']:failures.append({'condition':cid,'kind':kind,'index':i,'result':row})
    summary=[]
    for (method,policy,budget),rs in sorted(groups.items()):
        primary=[x for r in rs for x in r['primary']];cold=[x for r in rs for x in r['cold']]
        baseline=[x for r in rs for x in read(ROOT/'results/baselines'/(r['base']+'.json'))['probes']]
        bm=metrics(baseline);bm.pop('requested_outputs');bm['text_generation_measured']=False
        immediate=[r['final'] for r in primary if r['final']['session_confirmed_targets']]
        no_receipt=[r['final'] for r in primary if not r['final']['session_confirmed_targets']]
        summary.append({'method':method,'policy':policy,'global_budget_per_stream':budget,'streams':len(rs),
            'actual_confirmations':sum(r['actual_confirmations'] for r in rs),'budget_ceiling_sum':budget*len(rs),
            'initial_question_targets':sum(len(r['initial_plan'].get('questions',[])) for r in primary),
            'primary':metrics([r['final'] for r in primary]),'cold':metrics(cold),'matched_missing_baseline':bm,
            'primary_with_session_confirmations':metrics(immediate),'primary_without_session_confirmations':metrics(no_receipt),
            'by_input_kind':{k:metrics([r['final'] for r in primary if r['query_kind']==k]) for k in sorted({r['query_kind'] for r in primary})}})
    regression=read(ROOT/'results/V04_FAILURE_REGRESSION.json')
    result={'groups':summary,'primary_failures':sum(r['kind']=='primary' for r in failures),'cold_failures':sum(r['kind']=='cold' for r in failures),
            'v04_regression':{'episodes':len(regression),'legacy_wrong':sum(r['legacy']['wrong'] for r in regression),
              'selective_initially_asks':sum(r['selective_before']['status']=='needs_confirmation' for r in regression),
              'immediate_correct':sum(r['selective_after']['correct'] for r in regression),'confirmations':sum(len(r['answers']) for r in regression),
              'cold_correct':sum(r['cold_without_receipts']['correct'] for r in regression),'cold_wrong':sum(r['cold_without_receipts']['wrong'] for r in regression)},
            'independent_focal_scenes':24,'condition_repetitions_are_not_independent_scenes':True,'eligible_for_inference':False}
    write(ROOT/'verification/SUMMARY.json',result);write(ROOT/'verification/FAILURES.json',failures)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':run()
