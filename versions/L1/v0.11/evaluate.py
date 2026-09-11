import argparse,itertools,json,platform,sys,time
from pathlib import Path
import numpy as np
from plm_l1_v011.core import observe
from plm_l1_v011.training import fit,calibrate
from plm_l1_v011.algebra import canonical,digest
from evaluation.tasks import ROOT,semantic_queries
from evaluation.metrics import measure,equal_count
from evaluation.integrity import verify_freeze

def write(path,x):
    with Path(path).open('x',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def disjoint(task):
    sets=[{canonical(r['context']) for r in task[n]} for n in ('train','selection','calibration','test')]
    if 'added' in task:sets.append({canonical(r['context']) for r in task['added']})
    return not any(a&b for a,b in itertools.combinations(sets,2))

def judge(r):
    checks=[{'name':'splits_disjoint','passed':r['splits_disjoint'],'kind':'integrity'}]
    for i,run in enumerate(r['runs']):
        checks.append({'name':f'{i}/candidate_cap','passed':1<=run['storage']['members']<=4,'kind':'contract'})
        for j,stage in enumerate(run['stages']):
            for kind in ('raw','gated'):
                s=stage[kind];ok=s['correct']+s['wrong']+s['abstained']==s['requests'] and s['accepted']==s['correct']+s['wrong'] and (s['selective_risk'] is None)==(s['accepted']==0)
                checks.append({'name':f'{i}/{j}/{kind}/accounting','passed':ok,'kind':'accounting'})
            if stage['kind']=='numeric' and stage['fraction']==0:
                checks.append({'name':f'{i}/{j}/erased_veto','passed':stage['raw']['accepted']==0,'kind':'control'})
            if not run['enabled']:
                checks.append({'name':f'{i}/{j}/zero_weights','passed':stage['raw']['accepted']==0,'kind':'control'})
    return checks

def evaluate_model(task,model,protocol):
    stages=[];start=time.perf_counter()
    def stage(kind,queries,fraction=None,mask_seed=None):
        predictions=[]
        for i,q in enumerate(queries):
            try:
                if kind=='numeric':p=model.decode(observe(model.encode(q['context']),fraction,mask_seed),threshold=0.)
                else:p=model.predict(q['context'],threshold=0.)
            except ValueError as e:p={'value':None,'confidence':0.,'reason':str(e),'members':[]}
            raw=p['value'];gated=raw if raw is not None and p['confidence']>=model.threshold else None
            predictions.append({'query_id':canonical(q['context']),'allowed':q['allowed'],'raw':raw,'gated':gated,
                                'confidence':p['confidence'],'reason':p['reason'] if gated==raw else 'empirical_risk_gate',
                                'candidate_values':[a['value'] for a in p['members']]})
            if kind=='complete':predictions[-1]['candidate_scores']=[a['scores'] for a in p['members']]
        record={'kind':kind,'fraction':fraction,'mask_seed':mask_seed,'predictions':predictions,
                'raw':measure([p['raw'] for p in predictions],[p['allowed'] for p in predictions]),
                'gated':measure([p['gated'] for p in predictions],[p['allowed'] for p in predictions])}
        stages.append(record)
    full=[{'context':r['context'],'allowed':[r['label']]} for r in task['test']]
    stage('complete',full);stage('semantic_missing',semantic_queries(task))
    unknown={f:'not-registered' for f in model.config['fields']};stage('unknown_values',[{'context':unknown,'allowed':[]}])
    if model.config['backend']=='ss':
        for fraction in protocol['numeric_fractions']:
            for rep in range(1 if fraction in (0.,1.) else protocol['independent_numeric_masks']):
                stage('numeric',full,fraction,f"{task['id']}/mask-{rep}")
    return stages,time.perf_counter()-start

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--development',action='store_true');p.add_argument('--limit',type=int);a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    tasks=json.loads((ROOT/'data'/('development.json' if a.development else 'evaluation.json')).read_text(encoding='utf-8'))
    if a.limit:
        if not a.development:raise ValueError('final_evaluation_cannot_be_limited')
        tasks=tasks[:a.limit]
    result={'schema':'plm-v011-evaluation','freeze_hash':'development' if a.development else verify_freeze(),'runs':[],
            'splits_disjoint':all(disjoint(t) for t in tasks),'eligible_for_inference':False,'saved_models':{}}
    performance={'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'linux_execution_performed':False},'runs':[]}
    for task in tasks:
        for after in ((False,True) if 'added' in task else (False,)):
            for representation,selector,backend in itertools.product(protocol['representations'],protocol['selection_axis'],protocol['backends']):
                configs=itertools.product(protocol['dimensions'],protocol['seeds']) if backend=='ss' else [(2048,'exact-kernel')]
                for dimension,seed in configs:
                    budgets=('per_candidate','fixed_total') if task['family']=='ambiguity' and selector=='validation' and backend=='ss' else ('per_candidate',)
                    for budget in budgets:
                        model,audit,perf=fit(task['train']+(task['added'] if after else []),task['selection'],representation=representation,selector=selector,backend=backend,dimension=dimension,seed=seed,budget=budget)
                        calibrate(model,task['calibration'],protocol['risk_target']);stages,elapsed=evaluate_model(task,model,protocol)
                        method='/'.join((representation,selector,backend))
                        row={'task_id':task['id'],'family':task['family'],'after':after,'method':method,'dimension':dimension if backend=='ss' else None,'seed':seed,'budget':budget,'enabled':True,
                             'training':model.training,'audit':audit,'calibration':model.calibration,'storage':model.storage(),'stages':stages,'fingerprint':model.fingerprint}
                        result['runs'].append(row);performance['runs'].append({'index':len(result['runs'])-1,**perf,'evaluation_seconds':elapsed})
                        if representation=='hybrid3' and selector=='validation' and backend=='ss' and dimension==2048 and seed==protocol['seeds'][0] and budget=='per_candidate':
                            name='roles' if task['family']=='roles' else 'ambiguity-after' if after else 'ambiguity-before' if task['family']=='ambiguity' and task['id'].endswith('/0') else None
                            if task['family']=='ambiguity' and not task['id'].endswith('/0'):name=None
                            if name:model.save(out/name);result['saved_models'][name]={'task_id':task['id'],'after':after,'fingerprint':model.fingerprint}
            print('completed',task['id'],'after',after,'runs',len(result['runs']),flush=True)
    # Actual zero-weight controls on five standard dependency tasks, not zero labels.
    for task in [t for t in tasks if t['family'] in ('unary','xor2','and2','switch3','parity3') and t['id'].endswith('/0')][:5]:
        model,audit,perf=fit(task['train'],task['selection'],representation='hybrid3',selector='validation',dimension=2048,seed=protocol['seeds'][0],enabled=False)
        calibrate(model,task['calibration']);stages,elapsed=evaluate_model(task,model,protocol)
        result['runs'].append({'task_id':task['id'],'family':task['family'],'after':False,'method':'hybrid3/validation/ss','dimension':2048,'seed':protocol['seeds'][0],'budget':'per_candidate','enabled':False,
                              'training':model.training,'audit':audit,'calibration':model.calibration,'storage':model.storage(),'stages':stages,'fingerprint':model.fingerprint})
        performance['runs'].append({'index':len(result['runs'])-1,**perf,'evaluation_seconds':elapsed})
    matched=[];groups={}
    for run in result['runs']:
        if not run['enabled'] or run['budget']!='per_candidate':continue
        for s in run['stages']:
            if s['kind'] not in ('complete','semantic_missing'):continue
            key=(run['task_id'],run['after'],s['kind'],run['method'].split('/')[1])
            if run['dimension'] is None or (run['dimension']==2048 and run['seed']==protocol['seeds'][0]):groups.setdefault(key,[]).append({'method':run['method'],**s})
    for key,rows in groups.items():matched.append({'group':key,**equal_count(rows)})
    result['matched_coverage']=matched;result['checks']=judge(result);result['all_checks_passed']=all(c['passed'] for c in result['checks'])
    result['result_digest']=digest(result)
    write(out/'EVALUATION.json',result);write(out/'PERFORMANCE.json',performance)
    print(json.dumps({'runs':len(result['runs']),'checks':len(result['checks']),'passed':result['all_checks_passed'],'digest':result['result_digest']}),flush=True)
    return 0 if result['all_checks_passed'] else 1

if __name__=='__main__':raise SystemExit(main())
