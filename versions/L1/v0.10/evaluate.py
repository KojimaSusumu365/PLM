"""Frozen v0.10 experiment; no tuning on final evaluation labels."""
import argparse,itertools,json,platform,sys,time
from pathlib import Path
import numpy as np
from evaluation.support import ROOT,data
from evaluation.integrity import verify_freeze
from evaluation.synthetic import run,without_timing
from evaluation.language import standard,baseline_rows,training_case,ambiguity_probe
from evaluation.metrics import equal_count
from plm_l1_v010.training import fit
from plm_l1_v010.base.component.algebra import canonical,digest

def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def splits_disjoint(tasks):
    for task in tasks:
        subsets=[{canonical(r['context']) for r in task[name]} for name in ('train','selection_validation','risk_calibration','evaluation')]
        if 'added_examples' in task:subsets.append({canonical(r['context']) for r in task['added_examples']})
        if any(a&b for a,b in itertools.combinations(subsets,2)):return False
    return True

def matched_coverage(results,tasks):
    task_lookup={t['id']:t for t in tasks};groups={};output=[]
    for r in results:
        if not r['selection_enabled']:continue
        key=(r['task_id'],r['dimension'],r['seed'],r['budget'],r['after_added_examples'])
        groups.setdefault(key,{})[r['method']]=r
    for key,rows in groups.items():
        for name,methods in (('matched_new',['ss_multi','symbolic_multi','ss_single']),('all_five',['ss_multi','symbolic_multi','ss_single','v09_single','v09_pooled'])):
            if not all(m in rows for m in methods):continue
            for stage in ('ungated','calibrated'):
                predictions={m:[p[stage+'_value'] for p in rows[m]['predictions']] for m in methods}
                output.append({'task_id':key[0],'dimension':key[1],'seed':key[2],'budget':key[3],'after_added_examples':key[4],
                               'comparison':name,'stage':stage,**equal_count(task_lookup[key[0]]['evaluation'],predictions)})
    return output

def judge(result):
    checks=[]
    def add(name,passed,kind):checks.append({'name':name,'passed':bool(passed),'kind':kind})
    for stage in ('read','direct_generation','roundtrip'):
        row=result['language_standard'][stage];add('standard/'+stage,row['correct']==row['requests'],'capability')
    for name,values in result['language_baselines'].items():
        for stage in ('read','direct_generation','roundtrip'):
            row=values[stage];add(name+'/'+stage,row['correct']==row['requests'],'regression')
    for method in ('ss_multi','symbolic_multi'):
        for after in (False,True):
            row=result['language_ambiguity'][method+('/after' if after else '/before')]['generation']
            add('language_ambiguity/'+method+'/'+str(after),row['correct']==row['requests'] if after else row['abstained']==row['requests'],'capability')
    add('four_way_data_disjointness',result['four_way_data_disjointness'],'integrity')
    for i,r in enumerate(result['synthetic']+result['ambiguity']):
        for stage in ('ungated','calibrated'):
            m=r[stage];add(f'{i}/{stage}/accounting',m['correct']+m['wrong']+m['abstained']==m['requests'] and m['accepted']==m['correct']+m['wrong'],'accounting')
        add(f'{i}/candidate_bound',r['audit']['used_candidates']<=4,'contract')
        if not r['selection_enabled']:
            add(f'{i}/zero_phase_veto',not r['audit']['supported'] and r['ungated']['accepted']==0,'control')
        if '/ambiguous/' in r['task_id'] and r['dimension']==2048 and r['budget']=='per_candidate' and r['method'] in ('ss_multi','symbolic_multi'):
            stage=r['ungated'];after=r['after_added_examples']
            add(f'{i}/ambiguity_resolution',stage['correct']==stage['requests'] if after else stage['abstained']==stage['requests'],'capability')
    add('inference_closed',result['eligible_for_inference'] is False,'contract')
    return checks

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--development',action='store_true');a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    split='development' if a.development else 'evaluation';freeze='development_unfrozen' if a.development else verify_freeze()
    tasks=data('dependencies_'+split);amb=data('ambiguity_'+split)
    result={'schema':'plm-l1-v010-results','freeze_hash':freeze,'eligible_for_inference':False,'synthetic':[],'ambiguity':[],
            'language_baselines':{},'language_ambiguity':{},'selection_audits':{},'four_way_data_disjointness':splits_disjoint(tasks+amb)}
    perf={'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'linux_execution_performed':False},'synthetic':[],'language':{}}
    for task in tasks:
        normal=task['train_count']==24 and task['flipped_labels']==0
        dims=protocol['standard_dimensions'] if normal else [protocol['stress_dimension']]
        seeds=protocol['standard_seeds'] if normal else protocol['standard_seeds'][:1]
        for d in dims:
            for seed in seeds:
                for method in protocol['methods']:
                    r,t=run(task,method,d,seed);result['synthetic'].append(r);perf['synthetic'].append(t)
        if normal:
            r,t=run(task,'ss_multi',2048,protocol['standard_seeds'][0],enabled=False);result['synthetic'].append(r);perf['synthetic'].append(t)
        print('dependency',task['id'],flush=True)
    for task in amb:
        for d in (512,2048):
            for budget in ('per_candidate','fixed_total'):
                for method in protocol['methods']:
                    for after in (False,True):
                        r,t=run(task,method,d,protocol['standard_seeds'][0],budget=budget,after=after)
                        result['ambiguity'].append(r);perf['synthetic'].append(t)
        print('ambiguity',task['id'],flush=True)
    result['matched_coverage']=matched_coverage(result['synthetic']+result['ambiguity'],tasks+amb)
    models={}
    for method in ('ss_multi','symbolic_multi','ss_single','v09_single'):
        start=time.perf_counter()
        m=fit(data('component_train'),data('single_development'),data('temporal_train'),data('lexicon'),method=method,selection_seed=protocol['standard_seeds'][0])
        models[method]=m;fit_seconds=time.perf_counter()-start;start=time.perf_counter()
        result['language_baselines'][method]=standard(m,baseline_rows(data(split)),full=False)
        result['selection_audits'][method]=without_timing(m.selection_audit)
        perf['language'][method]={'fit_seconds':fit_seconds,'baseline_seconds':time.perf_counter()-start}
        print('language baseline',method,result['language_baselines'][method]['read'],flush=True)
    start=time.perf_counter();result['language_standard']=standard(models['ss_multi'],data(split))
    perf['language']['standard_full_seconds']=time.perf_counter()-start
    models['ss_multi'].save(out/'model');result['model_fingerprint']=models['ss_multi'].fingerprint
    result['model_metadata']=models['ss_multi'].meta
    for method in ('ss_multi','symbolic_multi','ss_single','v09_single'):
        for after in (False,True):
            start=time.perf_counter()
            m=fit(*training_case(after),data('lexicon'),method=method,selection_seed=protocol['standard_seeds'][0])
            name=method+('/after' if after else '/before')
            result['language_ambiguity'][name]=ambiguity_probe(m,split)
            result['language_ambiguity'][name]['model_metadata']=m.meta
            perf['language'][name]={'fit_and_probe_seconds':time.perf_counter()-start}
            if method=='ss_multi':m.save(out/('ambiguity-after' if after else 'ambiguity-before'))
            print('language ambiguity',name,result['language_ambiguity'][name]['generation'],flush=True)
    result['checks']=judge(result);result['all_checks_passed']=all(c['passed'] for c in result['checks'])
    result['result_digest']=digest(result)
    write(out/'EVALUATION.json',result);write(out/'PERFORMANCE.json',perf)
    print(json.dumps({'digest':result['result_digest'],'checks':len(result['checks']),'passed':result['all_checks_passed']}),flush=True)
    return 0 if result['all_checks_passed'] else 1

if __name__=='__main__':raise SystemExit(main())
