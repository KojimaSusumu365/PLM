"""Post-freeze aggregation and benchmarks. Does not tune the final experiment."""
import argparse,json,statistics,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ss_multicode.algebra import canonical
from ss_multicode.learning import Learner
from ss_active.session import Session,feedback
from evaluation.integrity import sha,write,verify
from evaluation.metrics import summarize
from evaluation.cases import truth_map
from evaluate import run


def add(a,b):
    for k,v in b.items():
        if isinstance(v,dict):add(a.setdefault(k,{}),v)
        else:a[k]=a.get(k,0)+v


def checkpoint(r,name):return next(s for s in r['checkpoints'] if s['name']==name)


def main():
    p=argparse.ArgumentParser();p.add_argument('--repeat',required=True);a=p.parse_args();verify();target=ROOT/'verification'
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'));runs=result['runs'];protocol=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    def inventory(folder):return {p.relative_to(folder).as_posix():sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='PERFORMANCE.json'}
    original=inventory(ROOT/'results');repeat=inventory(Path(a.repeat).resolve());assert original==repeat and len(original)==260
    write(target/'REPEATABILITY.json',{'all_equal':True,'files':original,'excluded':['PERFORMANCE.json'],'two_full_runs':True,'teachers_per_full_run':157696})
    baseline=json.loads((target/'BASELINE.json').read_text(encoding='utf-8'));changed=[n for n,h in baseline['previous_files'].items() if sha(ROOT.parent/n)!=h];assert not changed
    write(target/'PRESERVATION.json',{'all_unchanged':True,'files_checked':len(baseline['previous_files']),'changed':changed})
    cases={(c['seed'],c['size']):c for c in json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
    names=['q4','q16','post_D','q20','q32','post_E'];summary=[]
    for size in protocol['sizes']:
        for world in protocol['worlds']:
            for strategy in protocol['strategies']:
                subset=[r for r in runs if (r['size'],r['world'],r['strategy'])==(size,world,strategy)];assert len(subset)==16
                for name in names:
                    metrics={};selection={'teacher_presentations':0,'unique_keys':0,'revisit_teachers':0,'explore_teachers':0,
                        'changed_keys_selected_unique':0,'changed_teachers_including_revisits':0,'pre_tentative_wrong':0,'direct_wrong_to_correct_events':0,'logical_contexts_scored':0};resource=[]
                    for r in subset:
                        s=checkpoint(r,name);add(metrics,s['metrics']);resource.append(s['resources']);b=s['acquired'];trace=r['trace'][:b]
                        keys={e['request']['selection']['selected_id'] for e in trace};changed_ids=set(cases[r['data_seed'],size]['changed_ids']) if world=='changed_pool16' else set()
                        selection['teacher_presentations']+=b;selection['unique_keys']+=len(keys);selection['changed_keys_selected_unique']+=len(keys&changed_ids)
                        for e in trace:
                            sel=e['request']['selection'];selection['revisit_teachers']+=int(sel['route']=='revisit');selection['explore_teachers']+=int(sel['route']=='explore');selection['changed_teachers_including_revisits']+=int(sel['selected_id'] in changed_ids)
                            wrong=e['before']['tentative'] is not None and e['before']['tentative']!=e['teacher_label'];selection['pre_tentative_wrong']+=int(wrong);selection['direct_wrong_to_correct_events']+=int(wrong and e['after']['tentative']==e['teacher_label']);selection['logical_contexts_scored']+=sel['diagnostics']['contexts_scored_this_call']
                    summary.append({'size':size,'world':world,'strategy':strategy,'checkpoint':name,'trajectories':16,'base_data_code_configurations':8,
                        'metrics':metrics,'selection':selection,'resources':{'coefficient_bytes_each':resource[0]['coefficient_bytes'],
                         'selection_state_json_bytes_range':[min(s['selection_state_json_bytes'] for s in resource),max(s['selection_state_json_bytes'] for s in resource)],
                         'ledger_entries_range':[min(s['ledger_entries'] for s in resource),max(s['ledger_entries'] for s in resource)]}})
    pairs=[]
    comparisons=[('ambiguity_once','random_once'),('mixed_once','random_once'),('mixed_revisit','random_once'),
                 ('mixed_once','ambiguity_once'),('ambiguity_revisit','ambiguity_once'),('mixed_revisit','mixed_once'),
                 ('mixed_revisit','ambiguity_revisit'),('mixed_revisit','ambiguity_once')]
    metrics=[('old_all','accepted_correct',True),('old_all','accepted_wrong',False),('old_all','tentative_correct',True),
             ('protected_old','accepted_correct',True),('never_taught','unseen_false_accept',False),('changed_pool','tentative_correct',True),
             ('first_block_corrected','tentative_correct',True),('post_D_relapsed_first_block','tentative_correct',True)]
    for size in protocol['sizes']:
        for world in protocol['worlds']:
            for lhs,rhs in comparisons:
                left=[r for r in runs if (r['size'],r['world'],r['strategy'])==(size,world,lhs)]
                for name in names:
                    for group,metric,higher in metrics:
                        values=[];blocks={}
                        for r in left:
                            other=next(s for s in runs if s['strategy']==rhs and all(s[k]==r[k] for k in ('data_seed','size','code_seed','world','acquisition_seed')))
                            delta=checkpoint(r,name)['metrics']['groups'][group][metric]-checkpoint(other,name)['metrics']['groups'][group][metric];values.append(delta);blocks.setdefault((r['data_seed'],r['code_seed']),[]).append(delta)
                        means=[statistics.mean(v) for v in blocks.values()];signed=[v if higher else -v for v in values];signed_means=[v if higher else -v for v in means]
                        pairs.append({'size':size,'world':world,'lhs':lhs,'rhs':rhs,'checkpoint':name,'group':group,'metric':metric,
                            'lhs_minus_rhs_sum':sum(values),'lhs_minus_rhs_mean':statistics.mean(values),'min':min(values),'max':max(values),
                            'wins_ties_losses_16':[sum(v>0 for v in signed),sum(v==0 for v in signed),sum(v<0 for v in signed)],
                            'acquisition_seed_averaged_deltas_8':means,'wins_ties_losses_8':[sum(v>0 for v in signed_means),sum(v==0 for v in signed_means),sum(v<0 for v in signed_means)],
                            'cohort_is_identical_only_for_revisit_toggle_when_group_is_corrected':group in ('first_block_corrected','post_D_relapsed_first_block') and (lhs,rhs) in (('ambiguity_revisit','ambiguity_once'),('mixed_revisit','mixed_once'))})
    with np.load(ROOT/'results/SCORES.npz',allow_pickle=False) as z:raw={k:z[k] for k in z.files if k.startswith('b')}
    controls=[]
    for size in protocol['sizes']:
        for world in protocol['worlds']:
            subset=[r for r in runs if (r['size'],r['world'],r['strategy'])==(size,world,'random_once')]
            for known,name in ((3,'base'),(4,'post_D'),(5,'post_E')):
                m={}
                for r in subset:
                    case=cases[r['data_seed'],size];b=next(b for b in result['bases'] if all(b[k]==r[k] for k in ('data_seed','size','code_seed')));score=raw[b['arrays'][str(known)]]
                    add(m,summarize(score,case,world,known,[],raw[b['arrays']['3']],score,[],[],[]))
                controls.append({'size':size,'world':world,'checkpoint':name,'metrics':m,'display_weighting':'8 actual base/control fits, each counted twice to match16 acquisition trajectories'})
    write(target/'SUMMARY.json',{'description':'Descriptive factorial contrasts. Corrected cohorts vary across exploration arms; do not interpret raw cohort-count differences across those arms as identical-cohort retention effects. Two acquisition seeds share each base state. Groups overlap. No p-values.',
                                 'rows':summary,'paired_comparisons':pairs,'no_acquisition_controls':controls,'result_digest':result['result_digest']})
    # Measurements are serial and run only after both full evaluations are finished.
    case=cases['active2-final-0',128];b=next(b for b in result['bases'] if b['data_seed']==case['seed'] and b['size']==128 and b['code_seed']=='active2-code-0');ctrl={int(k):raw[v] for k,v in b['arrays'].items()};bench=[]
    for rep in range(3):
        for strategy in protocol['strategies']:
            expected=next(r for r in runs if r['data_seed']==case['seed'] and r['size']==128 and r['code_seed']=='active2-code-0' and r['world']=='stationary' and r['acquisition_seed']=='active2-acq-0' and r['strategy']==strategy)
            base=Learner.load(ROOT/'results/base-s128');base.model.raw([r['context'] for r in case['pool']])
            r,t=run(base,case,'stationary',strategy,'active2-acq-0',expected['config'],expected['config_index'],ctrl,{},ROOT,False)
            assert r['final_session_fingerprint']==expected['final_session_fingerprint']
            bench.append({'rep':rep,'strategy':strategy,'times':t,'resources_final':r['checkpoints'][-1]['resources']})
    write(target/'BENCHMARK.json',{'environment':json.loads((ROOT/'results/PERFORMANCE.json').read_text(encoding='utf-8'))['environment'],
        'single_process_warm_cache':True,'rows':bench,'extra_teacher_presentations':8160,
        'not_measured':['total_process_RSS','total_FLOPs','other_OS'],'logical_context_counts_exclude_selection_revalidation_and_evaluation':True})
    # Demonstrate an actually selected revisit, not an oracle-chosen correction.
    example=ROOT/'examples';example.mkdir(exist_ok=False)
    r=next(r for r in runs if r['saved'] and r['size']==128 and r['strategy']=='mixed_revisit')
    candidates=[i for i,e in enumerate(r['trace']) if e['request']['selection']['route']=='revisit'];assert candidates
    index=candidates[0];s=Session.load(ROOT/'results/s128-mixed_revisit-post_D')
    for e in r['trace'][16:index]:q=s.ask();assert q==e['request'];s=s.answer(q,feedback(q,e['teacher_label']))
    q=s.ask();assert q==r['trace'][index]['request'] and q['selection']['route']=='revisit';fb=feedback(q,r['trace'][index]['teacher_label']);new=s.answer(q,fb)
    s.save(example/'before-revisit');write(example/'request.json',q);write(example/'feedback.json',fb);write(example/'selection-state.json',s.selection_state)
    write(example/'queries.json',[q['selection']['context']]);write(example/'config.json',r['config']);write(example/'pool.json',case['pool'])
    write(example/'EXPECTED.json',{'session_before':s.fingerprint,'session_after':new.fingerprint,'acquisition_index_zero_based':index,'route':'revisit',
        'before':s.learner.model.predict([q['selection']['context']]),'after':new.learner.model.predict([q['selection']['context']]),
        'synthetic_external_teacher_example_not_truth_authentication':True,'extra_example_teacher_presentations':index-16+1})
    print(json.dumps({'repeat_files':len(original),'preserved_files':len(baseline['previous_files']),'summary_rows':len(summary),'paired_comparisons':len(pairs),'benchmark_runs':len(bench),'example_revisit_index':index}),flush=True)


if __name__=='__main__':main()
