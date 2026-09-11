import argparse,time
from pathlib import Path
from ss_partial.runtime import PartialModel
from ss_partial.contract import to_meaning
from evaluation.integrity import ROOT,read,write,verify
from evaluation.experiment02 import prepare_inputs,base_store,trial,historical,score

def summarize(rows):
    groups=[]
    for condition,method in sorted({(r['condition'],r['method']) for r in rows}):
        rs=[r for r in rows if (r['condition'],r['method'])==(condition,method)]
        results=[r[k] for r in rs for k in ('immediate','later','anchor')]
        groups.append({'condition':condition,'method':method,'trials':len(rs),
            'committed':sum(r['committed'] for r in rs),'held':sum(not r['committed'] for r in rs),
            'committed_but_target_not_correct':sum(r['committed_but_target_not_correct'] for r in rs),
            'immediate_correct':sum(r['immediate']['correct'] for r in rs),'later_correct':sum(r['later']['correct'] for r in rs),
            'anchor_correct':sum(r['anchor']['correct'] for r in rs),'wrong_generated_documents':sum(r['wrong'] for r in results),
            'held_documents':sum(r['status']=='held' for r in results),'correct_documents':sum(r['correct'] for r in results),
            'generated_texts':sum(o['generation']['status']=='generated' for r in results for o in r['outputs']),
            'requested_texts':6*len(rs),'ss_unchanged_on_all_holds':all(r['ss_memory_unchanged_on_hold'] for r in rs),
            'cost':{k:sum(r['cost'][k] for r in rs) for k in rs[0]['cost']}})
    return groups

def acceptance(groups,plan):
    get=lambda c,m:next(g for g in groups if (g['condition'],g['method'])==(c,m))
    clean=get('clean','guard');mild=get('independent1','guard')
    checks={'clean_guard_all_correct':clean['committed']==clean['trials'] and clean['later_correct']==clean['trials'],
        'mild_guard_commit_rate':mild['committed']/mild['trials']>=plan['minimum_mild_commit_rate'],
        'all_anchor_memories_preserved':all(g['anchor_correct']==g['trials'] for g in groups),
        'held_ss_memory_unchanged':all(g['ss_unchanged_on_all_holds'] for g in groups)}
    for c in plan['primary_faults']:
        guard=get(c,'guard')
        checks[c+'_no_bad_guard_commit']=guard['committed_but_target_not_correct']==0
        checks[c+'_less_bad_than_single']=guard['committed_but_target_not_correct']<get(c,'single')['committed_but_target_not_correct']
        checks[c+'_no_wrong_guard_text']=guard['wrong_generated_documents']==0
    return {'passed':all(checks.values()),'checks':checks,'scope':'Primary criteria only, not a guarantee for shared corruption',
            'eligible_for_inference':False}

def run(out,development=False):
    start=time.perf_counter();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    frozen=None if development else verify()
    plan=read(ROOT/'evaluation/PROTOCOL.json');split='development' if development else 'evaluation'
    cases=read(ROOT/'data/GUARD_CORPUS.json')['splits'][split]
    model=PartialModel.load(ROOT/'model');packets,inputs=prepare_inputs(model,cases)
    write(out/'INPUTS.json',inputs)
    seeds=[0] if development else plan['memory_seeds']
    rows=[];index=[];bases=[]
    focal=[c for c in cases if c['kind']=='focal'];anchors=[c for c in cases if c['kind']=='anchor']
    if development:focal=focal[:2]
    for seed in seeds:
        base,receipts=base_store(model,cases,packets,seed)
        base.save(out/'bases'/str(seed))
        before=[]
        for c in cases:
            if c['kind']=='background':continue
            expected={**c,'known':c['initial'],'meaning':to_meaning(c['initial'],model.codec.candidates)}
            before.append({'case_id':c['id'],'result':score(model,base,expected,packets[(c['id'],'query')])})
        bases.append({'seed':seed,'fingerprint':base.fingerprint,'receipts':receipts,'initial_generation':before})
        for condition in plan['conditions']:
            for method in plan['methods']:
                for i,c in enumerate(focal):
                    ident=f'{len(rows):04d}';path=out/'runs'/ident
                    r=trial(model,base,cases,packets,c,anchors[i%len(anchors)],seed,condition,method,path)
                    write(path/'RESULT.json',r);rows.append(r);index.append(ident)
            print({'seed':seed,'condition':condition,'trials':len(rows)},flush=True)
    groups=summarize(rows)
    for name,value in [('SUMMARY.json',groups),('BASES.json',bases),('INDEX.json',{'runs':index,'frozen_digest':frozen,'development':development}),
                       ('DECISION.json',acceptance(groups,plan))]:write(out/name,value)
    if not development:write(out/'HISTORICAL.json',historical(model,cases,packets,out/'historical'))
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start,'not_hardware_throughput':True})
    print({'complete':True,'trials':len(rows),'decision':acceptance(groups,plan)},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--development',action='store_true')
    a=p.parse_args();run(a.out,a.development)
