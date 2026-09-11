import argparse,time
from pathlib import Path
from evaluation.integrity import ROOT,read,write,verify
from evaluation.experiment import run_case
from ss_partial.runtime import PartialModel

def summarize(rows):
    groups=[]
    for condition,method in sorted({(r['condition'],r['method']) for r in rows}):
        rs=[r for r in rows if (r['condition'],r['method'])==(condition,method)]
        groups.append({'condition':condition,'method':method,'cases':len(rs),'learned':sum(r['teacher_learned'] for r in rs),
            'wrong_teachers':sum(r['teacher_correct'] is False for r in rs),'correct':sum(r['result']['correct'] for r in rs),
            'wrong':sum(r['result']['wrong'] for r in rs),'held':sum(r['result']['status']=='held' for r in rs),
            'generated_outputs':sum(o['generation']['status']=='generated' for r in rs for o in r['result']['outputs']),
            'requested_outputs':2*len(rs),'wrong_sync_frames':sum(r[k]['wrong_aligned_frames'] for r in rs for k in ('teacher_sync','query_sync') if r[k]),
            'aligned_frames':sum(r[k]['aligned_frames'] for r in rs for k in ('teacher_sync','query_sync') if r[k]),
            'failure_stages':{stage:sum(r['result']['failure_stage']==stage for r in rs) for stage in sorted({str(r['result']['failure_stage']) for r in rs if r['result']['failure_stage'] is not None})}})
    return groups

def acceptance(groups,plan):
    get=lambda c,m:next(r for r in groups if (r['condition'],r['method'])==(c,m))
    main=[r for r in groups if r['condition'] in plan['main_conditions'] and r['method']=='ss_estimated'];rules=[]
    rules.append({'name':'direct_all_correct','passed':all(get(c,'direct')['correct']==get(c,'direct')['cases'] for c in plan['main_conditions'])})
    for c in plan['main_conditions']:
        g=get(c,'ss_estimated');threshold=plan['acceptance']['ss_'+c+'_correct_rate_min']
        rules.append({'name':'ss_'+c+'_correct_rate','passed':g['correct']/g['cases']>=threshold,'observed':g['correct']/g['cases'],'threshold':threshold})
    rules.append({'name':'ss_main_no_wrong_generation','passed':sum(r['wrong'] for r in main)==0})
    rules.append({'name':'ss_main_no_wrong_teacher_update','passed':sum(r['wrong_teachers'] for r in main)==0})
    rules.append({'name':'ss_main_no_wrong_alignment','passed':sum(r['wrong_sync_frames'] for r in main)==0})
    hard=[get(c,'ss_estimated') for c in plan['hard_negative_conditions']]
    rules.append({'name':'hard_negative_no_updates','passed':sum(r['learned'] for r in hard)==0})
    rules.append({'name':'hard_negative_no_generation','passed':sum(r['generated_outputs'] for r in hard)==0})
    return {'passed':all(x['passed'] for x in rules),'checks':rules,'eligible_for_inference':False}

def run(out,development=False):
    start=time.perf_counter();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    frozen=None if development else verify();plan=read(ROOT/'evaluation/PROTOCOL.json');data=read(ROOT/'data/CORPUS.json');model=PartialModel.load(ROOT/'model')
    cases=data['splits']['development' if development else 'evaluation'];seeds=[1100] if development else plan['channel_seeds'];jobs=[]
    for case in cases:
        for seed in seeds:
            for condition in plan['main_conditions']:
                for method in plan['methods']:jobs.append((case,condition,seed,method))
    for case in cases[:plan['stress_case_count']]:
        for condition in plan['stress_conditions']:jobs.append((case,condition,1300 if development else plan['stress_seed'],'ss_estimated'))
    rows=[];index=[]
    for i,(case,condition,seed,method) in enumerate(jobs):
        name=f'{i:04d}';p=out/'runs'/name;r=run_case(model,case,condition,seed,method,p);write(p/'RESULT.json',r);rows.append(r);index.append(name)
        if (i+1)%10==0 or i+1==len(jobs):print({'done':i+1,'total':len(jobs),'last':method+'/'+condition,'correct':r['result']['correct']},flush=True)
    groups=summarize(rows);write(out/'SUMMARY.json',groups);write(out/'INDEX.json',{'runs':index,'frozen_digest':frozen,'development':development})
    decision=None if development else acceptance(groups,plan)
    if decision is not None:write(out/'DECISION.json',decision)
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start});print({'complete':True,'runs':len(rows),'decision':decision},flush=True)
    return rows
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--development',action='store_true');a=p.parse_args();run(a.out,a.development)
