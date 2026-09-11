"""Post-freeze descriptive aggregation; does not choose/tune any experiment setting."""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import sha, verify, write
from evaluation.cases import truth_map
from ss_multicode.learning import Learner
from ss_active.session import Session, feedback


def add(a, b):
    for k, v in b.items():
        if isinstance(v, dict): add(a.setdefault(k, {}), v)
        else: a[k] = a.get(k, 0) + v


def snap(run, budget, stage):
    return next(c for c in run['checkpoints'] if c['budget'] == budget and c['stage'] == stage)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--repeat', required=True); a = p.parse_args()
    verify(); target = ROOT/'verification'
    result = json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    def files(folder):
        return {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob('*'))
                if p.is_file() and '__pycache__' not in p.parts and p.name != 'PERFORMANCE.json'}
    original = files(ROOT/'results'); repeated = files(Path(a.repeat).resolve())
    assert original == repeated
    write(target/'REPEATABILITY.json', {'all_equal': True, 'files': original, 'excluded': ['PERFORMANCE.json'],
                                       'two_full_runs': True, 'actual_teachers_per_run': 172032})
    baseline = json.loads((target/'BASELINE.json').read_text(encoding='utf-8'))
    changed = [n for n,h in baseline['previous_files'].items() if sha(ROOT.parent/n) != h]
    assert not changed
    write(target/'PRESERVATION.json', {'all_unchanged': True, 'files_checked': len(baseline['previous_files']), 'changed': changed})
    cases = {(c['seed'], c['size']):c for c in json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
    summary = []
    for size in (64,128):
        for world in ('stationary','changed_pool16'):
            for strategy in ('random','ambiguity','disagreement'):
                runs = [r for r in result['runs'] if (r['size'],r['scenario'],r['strategy']) == (size,world,strategy)]
                assert len(runs) == 16
                for budget in (0,4,16,32):
                    teaching = {'requests':0,'pre_tentative_wrong':0,'pre_tentative_abstained':0,
                                'pre_accepted_correct':0,'post_tentative_correct':0,
                                'direct_wrong_to_correct':0,'changed_items_selected':0}
                    logical = 0
                    for r in runs:
                        changed_ids = set(cases[r['data_seed'],r['size']]['changed_ids']) if world == 'changed_pool16' else set()
                        for e in r['trace'][:budget]:
                            teaching['requests'] += 1
                            teaching['pre_tentative_wrong'] += int(e['before']['tentative'] is not None and e['before']['tentative'] != e['truth'])
                            teaching['pre_tentative_abstained'] += int(e['before']['tentative'] is None)
                            teaching['pre_accepted_correct'] += int(e['before']['accepted'] == e['truth'])
                            teaching['post_tentative_correct'] += int(e['after']['tentative'] == e['truth'])
                            teaching['direct_wrong_to_correct'] += int(e['before']['tentative'] is not None and e['before']['tentative'] != e['truth'] and e['after']['tentative'] == e['truth'])
                            teaching['changed_items_selected'] += int(e['request']['selection']['selected_id'] in changed_ids)
                            logical += e['request']['selection']['diagnostics']['contexts_scored_this_call']
                    for stage in ('after_acquisition','after_challenge'):
                        metrics = {}
                        for r in runs: add(metrics, snap(r,budget,stage)['metrics'])
                        summary.append({'size':size,'scenario':world,'strategy':strategy,'budget':budget,'stage':stage,
                                        'trajectories':16,'base_data_code_configurations':8,'metrics':metrics,
                                        'teacher_selection':teaching,'logical_contexts_scored_sum':logical,
                                        'logical_contexts_scored_per_trajectory':logical//16})
    pairs = []
    for size in (64,128):
        for world in ('stationary','changed_pool16'):
            for lhs,rhs in (('ambiguity','random'),('disagreement','random'),('disagreement','ambiguity')):
                left = [r for r in result['runs'] if (r['size'],r['scenario'],r['strategy']) == (size,world,lhs)]
                for budget in (4,16,32):
                    for stage in ('after_acquisition','after_challenge'):
                        for group,metric,higher in (('old_all','tentative_correct',True),('old_all','accepted_correct',True),
                                                   ('old_all','accepted_wrong',False),('protected_old','tentative_correct',True),
                                                   ('never_taught','unseen_false_accept',False)):
                            values = []; blocks = {}
                            for r in left:
                                s = next(s for s in result['runs'] if s['strategy'] == rhs and all(s[k] == r[k] for k in ('size','scenario','data_seed','code_seed','acquisition_seed')))
                                delta = snap(r,budget,stage)['metrics']['groups'][group][metric]-snap(s,budget,stage)['metrics']['groups'][group][metric]
                                values.append(delta); blocks.setdefault((r['data_seed'],r['code_seed']),[]).append(delta)
                            blockmeans = [statistics.mean(v) for v in blocks.values()]
                            signed = [v if higher else -v for v in values]; signedblocks = [v if higher else -v for v in blockmeans]
                            pairs.append({'size':size,'scenario':world,'lhs':lhs,'rhs':rhs,'budget':budget,'stage':stage,'group':group,'metric':metric,
                                          'lhs_minus_rhs_sum':sum(values),'lhs_minus_rhs_mean':statistics.mean(values),'min':min(values),'max':max(values),
                                          'wins_ties_losses_16_shared_start_trajectories':[sum(v>0 for v in signed),sum(v==0 for v in signed),sum(v<0 for v in signed)],
                                          'acquisition_seed_averaged_deltas_8_base_configurations':blockmeans,
                                          'wins_ties_losses_8_base_configurations':[sum(v>0 for v in signedblocks),sum(v==0 for v in signedblocks),sum(v<0 for v in signedblocks)]})
    write(target/'SUMMARY.json', {'description':'Descriptive counts, overlapping groups; two acquisition seeds share each of eight starting data/code states. No p-values or independence assumption.',
                                  'result_digest':result['result_digest'],'rows':summary,'paired_comparisons':pairs})
    # Serial warm-start measurements AFTER the two evaluations finish. These are not equal-FLOP comparisons.
    case = cases['active-final-0',128]; truth = truth_map(case,'stationary'); bench=[]
    for rep in range(3):
        for strategy in ('random','ambiguity','disagreement'):
            session = Session(Learner.load(ROOT/'results/base-s128'),case['pool'],strategy,'active-acq-0')
            session.learner.model.raw([r['context'] for r in case['pool']])
            selection_seconds = response_seconds = 0.
            for i in range(32):
                t=time.perf_counter(); request=session.ask(); selection_seconds+=time.perf_counter()-t
                label=truth[request['selection']['selected_id']]
                t=time.perf_counter(); session=session.answer(request,feedback(request,label)); response_seconds+=time.perf_counter()-t
            queries=[r['context'] for r in case['pool']]; t=time.perf_counter()
            for i in range(20): session.learner.model.predict(queries)
            query_ms=1000*(time.perf_counter()-t)/(20*len(queries))
            expected=next(r for r in result['runs'] if r['size']==128 and r['data_seed']=='active-final-0' and r['code_seed']=='active-code-0' and r['scenario']=='stationary' and r['acquisition_seed']=='active-acq-0' and r['strategy']==strategy)
            assert session.fingerprint==expected['final_session_fingerprint']
            bench.append({'rep':rep,'strategy':strategy,'selection_seconds_32_requests':selection_seconds,
                          'response_seconds_32_teachers_including_selection_revalidation':response_seconds,
                          'query_ms_per_context_batched128':query_ms,'storage':session.learner.storage(),
                          'session_json_bytes':len(json.dumps(session.state,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))})
    write(target/'BENCHMARK.json', {'environment':json.loads((ROOT/'results/PERFORMANCE.json').read_text(encoding='utf-8'))['environment'],
                                   'rows':bench,'single_process_warm_cache':True,'teachers_separate_from_main_evaluation':288,
                                   'logical_selection_counts_at32':{'random':32,'active_pool64':1552,'active_pool128':3600},
                                   'not_measured':['total_process_RSS','FLOPs','other_OS'],
                                   'response_revalidates_selection_so_logical_counts_are_not_actual_total_scoring_calls':True})
    example=ROOT/'examples'; example.mkdir(exist_ok=False)
    s=Session.load(ROOT/'results/s128-disagreement-b0'); req=s.ask(); fb=feedback(req,truth[req['selection']['selected_id']]); new=s.answer(req,fb)
    write(example/'pool.json',s.pool); write(example/'request.json',req); write(example/'feedback.json',fb)
    write(example/'queries.json',[req['selection']['context']]); write(example/'EXPECTED.json',{'session_before':s.fingerprint,'session_after':new.fingerprint,
        'prediction_before':s.learner.model.predict([req['selection']['context']]),'prediction_after':new.learner.model.predict([req['selection']['context']]),
        'feedback_is_an_offline_synthetic_teacher_example_not_an_online_truth_service':True})
    print(json.dumps({'repeat_files':len(original),'preserved_files':len(baseline['previous_files']),'summary_rows':len(summary),'paired_comparisons':len(pairs),'benchmark_runs':len(bench)},indent=2))


if __name__=='__main__': main()
