import copy,time
from plm_l1_v010.memory import fit_memory,calibrate_gate
from .metrics import score,curves

def pairs(rows): return [(r['context'],r['label']) for r in rows]

def without_timing(obj):
    if isinstance(obj,dict): return {k:without_timing(v) for k,v in obj.items() if k!='wall_seconds'}
    if isinstance(obj,list): return [without_timing(v) for v in obj]
    return obj

def run(task,method,dimension,seed,*,budget='per_candidate',enabled=True,after=False):
    train=task['train']+(task['added_examples'] if after else [])
    started=time.perf_counter()
    model=fit_memory(pairs(train),pairs(task['selection_validation']),method=method,dimension=dimension,seed=seed,budget=budget,selection_enabled=enabled)
    fit_seconds=time.perf_counter()-started; started=time.perf_counter()
    calibration=calibrate_gate(model,pairs(task['risk_calibration']))
    calibration_seconds=time.perf_counter()-started; started=time.perf_counter()
    raw=[model.predict(r['context'],threshold=0.) for r in task['evaluation']]
    gated=[model.predict(r['context']) for r in task['evaluation']]
    query_seconds=time.perf_counter()-started
    gold=[r['label'] for r in task['evaluation']]; storage=model.storage(); heap=storage.pop('owned_heap_bytes')
    ood=[model.predict(r['context']) for r in task.get('ood',[])]
    result={'task_id':task['id'],'method':method,'dimension':dimension,'seed':seed,'budget':budget,'selection_enabled':enabled,'after_added_examples':after,
            'training_rows':len(train),'selection_validation_rows':len(task['selection_validation']),'risk_calibration_rows':len(task['risk_calibration']),
            'audit':without_timing(model.audit),'ungated':score([a['value'] for a in raw],gold),'calibrated':score([a['value'] for a in gated],gold),
            'calibration':calibration,'risk_coverage_curve':curves(raw,gold),'storage':storage,
            'predictions':[{'context':r['context'],'gold':r['label'],'ungated_value':a['value'],'calibrated_value':b['value'],
                            'reason':b['reason'],'confidence':a['confidence'],'member_values':[m['value'] for m in a['members']]}
                           for r,a,b in zip(task['evaluation'],raw,gated)],
            'ood_requests':len(ood),'ood_accepted':sum(a['value'] is not None for a in ood)}
    perf={'task_id':task['id'],'method':method,'dimension':dimension,'seed':seed,'budget':budget,'after_added_examples':after,
          'fit_seconds':fit_seconds,'calibration_seconds':calibration_seconds,'two_pass_query_seconds':query_seconds,'memory_owned_heap_bytes':heap}
    return result,perf
