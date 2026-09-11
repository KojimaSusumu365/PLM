"""Post-evaluation accounting and immutable-file evidence, never model tuning."""
import argparse,collections,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.integrity import sha,verify_freeze
from plm_l1_v010.runtime import CommitteeModel
from plm_l1_v010.portability import compare
sys.path.insert(0,str(ROOT/'tests'))
from test_v010 import perturb

def write(name,value):
    with (ROOT/'verification'/name).open('x',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def totals(rows):
    result={k:sum(r[k] for r in rows) for k in ('requests','correct','wrong','abstained','accepted')}
    result['coverage']=result['accepted']/result['requests'] if result['requests'] else None
    result['selective_risk']=result['wrong']/result['accepted'] if result['accepted'] else None
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--repeat',required=True);a=p.parse_args()
    repeated=Path(a.repeat).resolve()
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    tasks={t['id']:t for t in json.loads((ROOT/'data/dependencies_evaluation.json').read_text(encoding='utf-8'))}
    groups={};aggregate=[]
    for r in result['synthetic']+result['ambiguity']:
        task=tasks.get(r['task_id'])
        category='ambiguity' if task is None else 'standard' if task['train_count']==24 and task['flipped_labels']==0 else 'stress'
        category=category if r['selection_enabled'] else 'zero_phase'
        key=(category,r['method'],r['dimension'],r['budget'],r['after_added_examples'])
        groups.setdefault(key,[]).append(r)
    for key,rows in sorted(groups.items()):
        aggregate.append(dict(zip(('category','method','dimension','budget','after_added_examples'),key),
            runs=len(rows),ungated=totals([r['ungated'] for r in rows]),calibrated=totals([r['calibrated'] for r in rows]),
            candidate_counts=dict(collections.Counter(r['audit']['used_candidates'] for r in rows)),
            state_bytes_range=[min(r['storage']['state_bytes'] for r in rows),max(r['storage']['state_bytes'] for r in rows)],
            numerical_weight_bytes_range=[min(r['storage']['numerical_weight_bytes'] for r in rows),max(r['storage']['numerical_weight_bytes'] for r in rows)],
            evaluation_risk_above_calibration_target_runs=sum(r['calibrated']['selective_risk'] is not None and r['calibrated']['selective_risk']>r['calibration']['risk_target'] for r in rows),
            ood_requests=sum(r['ood_requests'] for r in rows),ood_accepted=sum(r['ood_accepted'] for r in rows)))
    matched=[]
    for name in ('matched_new','all_five'):
        for stage in ('ungated','calibrated'):
            for category in ('dependency','ambiguity_before','ambiguity_after'):
                rows=[r for r in result['matched_coverage'] if r['comparison']==name and r['stage']==stage and
                      (('ambiguity_after' if r['after_added_examples'] else 'ambiguity_before') if '/ambiguous/' in r['task_id'] else 'dependency')==category]
                methods=list(rows[0]['metrics']) if rows else []
                matched.append({'comparison':name,'stage':stage,'category':category,'groups':len(rows),
                    'zero_common_coverage_groups':sum(r['accepted_per_method']==0 for r in rows),
                    'accepted_per_method':sum(r['accepted_per_method'] for r in rows),
                    'wrong_by_method':{m:sum(r['metrics'][m]['wrong'] for r in rows) for m in methods},
                    'scope':'Equal number answered, not identical inputs; zero-common groups contribute no risk comparison.'})
    paired={}
    for r in result['synthetic']+result['ambiguity']:
        if not r['selection_enabled']:continue
        key=(r['task_id'],r['dimension'],r['seed'],r['budget'],r['after_added_examples'])
        paired.setdefault(key,{})[r['method']]=r
    differences=[]
    for key,rows in paired.items():
        x=rows['ss_multi'];y=rows['symbolic_multi']
        if any(a[s]!=b[s] for a,b in zip(x['predictions'],y['predictions']) for s in ('ungated_value','calibrated_value')):
            differences.append({'condition':key,'ss_multi':{'ungated':x['ungated'],'calibrated':x['calibrated']},'symbolic_multi':{'ungated':y['ungated'],'calibrated':y['calibrated']}})
    language_ambiguity={}
    for name,r in result['language_ambiguity'].items():
        meta=r['model_metadata']['training']
        language_ambiguity[name]={k:r[k] for k in ('generation','component_training_pairs','selection_validation_pairs','temporal_training_pairs','storage')}
        language_ambiguity[name].update({k:meta[k] for k in ('joint_plausible_count','joint_candidate_space_complete','member_count','supported','single_candidate_ablation')})
        language_ambiguity[name]['reasons']=dict(collections.Counter(d['reason'] for d in r['details']))
    summary={'result_digest':result['result_digest'],'checks_by_kind':dict(collections.Counter(c['kind'] for c in result['checks'])),
             'scalar_fitted_conditions':len(result['synthetic'])+len(result['ambiguity']),
             'scalar_aggregates':aggregate,'matched_coverage':matched,'ss_vs_symbolic_paired_conditions':len(paired),
             'ss_vs_symbolic_prediction_differences':differences,'language_standard':result['language_standard'],
             'language_baselines':result['language_baselines'],'language_ambiguity':language_ambiguity,
             'scope':'Posthoc aggregation of frozen raw results; no new threshold or source changes.'}
    write('RESULT_SUMMARY.json',summary)
    files=[]
    for f in sorted((ROOT/'results').rglob('*')):
        if not f.is_file() or f.name=='PERFORMANCE.json':continue
        rel=f.relative_to(ROOT/'results');g=repeated/rel
        files.append({'file':rel.as_posix(),'sha256':sha(f),'repeat_sha256':sha(g),'equal':sha(f)==sha(g)})
    assert files and all(r['equal'] for r in files)
    write('REPEATABILITY.json',{'two_full_v010_evaluations':True,'same_source_freeze':verify_freeze(),'files':files,
                              'excluded':['PERFORMANCE.json (environment, wall times and heap)'],
                              'older_full_numeric_evaluations_rerun':False})
    expected=json.loads((ROOT/'verification/PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
    changed=[n for n,h in expected.items() if not (ROOT.parent/n).is_file() or sha(ROOT.parent/n)!=h]
    assert not changed,changed
    write('PRESERVATION_CHECK.json',{'previous_files_checked':len(expected),'changed':changed,'all_preserved':True,
          'excluded_shared_history_document':'PLM-SS-LANGUAGE-DIRECTION.md (append-only planned)',
          'vendor_v09_sha256':sha(ROOT/'vendor/PLM-L1-v0.9.zip')})
    model=CommitteeModel.load(ROOT/'results/model');tiny=perturb(model,'ulp');large=perturb(model,.01)
    probes=['太郎が花子を助けた。その後、花子が健太を褒めた。','太郎が花子を助けた。花子が健太を褒めた。','']
    small=compare(model,tiny,probes);big=compare(model,large,probes)
    assert small['functional_passed'] and not small['exact_fingerprint_equal'] and not big['functional_passed']
    write('PORTABILITY_CONTROLS.json',{'one_ulp':small,'large_change':big,'linux_execution_performed':False,
                                     'scope':'Controlled local perturbation only, not cross-OS validation.'})
    print(json.dumps({'conditions':summary['scalar_fitted_conditions'],'ss_symbolic_difference_conditions':len(differences),
                      'repeat_files_equal':len(files),'previous_files_preserved':len(expected)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
