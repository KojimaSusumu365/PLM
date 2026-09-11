"""Separate phase memories, unanimous decisions, optional empirically calibrated gate."""
from collections import Counter
import numpy as np
from .base.component.algebra import canonical,require
from .base.component.banked import fit_banked
from .base.thresholds import MIN_SCORE,MIN_MARGIN,MIN_PROOF
from .base.selection import select as old_select
from .selection import select_candidates
from .policy import DEFAULT_RISK_TARGET

class MemoryCommittee:
    def __init__(self,memories,audit):
        require(1<=len(memories)<=4,'invalid_committee_size')
        self.memories=tuple(memories); self.audit=audit
        self.supported=audit['supported']; self.threshold=0.

    def predict(self,context,*,threshold=None):
        answers=[m.recall(context) for m in self.memories]
        values=[a['value'] for a in answers]
        agree=self.supported and all(v is not None for v in values) and len(set(values))==1
        confidence=0.
        if agree:
            confidence=min(min(p['score']-MIN_SCORE,p['margin']-MIN_MARGIN,
                               p['evidence']-MIN_PROOF if p['evidence_required'] else float('inf'))
                           for a in answers for p in a['projections'])
            confidence=round(max(0.,confidence),8)
        gate=self.threshold if threshold is None else threshold
        accepted=agree and confidence>=gate
        return {'value':values[0] if accepted else None,'unanimous':bool(agree),'confidence':round(confidence,8),
                'members':[{'id':f'hypothesis:{i}','value':v,'projections':a['projections']} for i,(v,a) in enumerate(zip(values,answers))],
                'reason':'accepted' if accepted else 'unsupported_committee' if not self.supported else 'candidate_disagreement_or_missing_support' if not agree else 'empirical_risk_gate',
                'eligible_for_inference':False}

    def storage(self):
        return {k:sum(m.storage()[k] for m in self.memories) for k in ('state_bytes','cache_capacity_bytes','owned_heap_bytes','numerical_weight_bytes')}

def fit_memory(train,validation,*,method='ss_multi',dimension=2048,seed='candidate-development-0',selection_enabled=True,budget='per_candidate'):
    require(method in ('ss_multi','symbolic_multi','ss_single','v09_single','v09_pooled'),'invalid_method')
    require(budget in ('per_candidate','fixed_total'),'invalid_budget_policy')
    if method.startswith('v09'):
        source=train+validation if method=='v09_pooled' else train
        leaves,old=old_select(source,dimension=dimension,seed=seed)
        selected=[leaves]; audit={'supported':True,'selected_masks':old['selected_masks'],'overflow':False,'retained_count':1,
                                 'method':method,'legacy_audit':old,'validation_labels_used':method=='v09_pooled'}
    else:
        selected,audit=select_candidates(train,validation,method='symbolic' if method=='symbolic_multi' else 'ss',dimension=dimension,seed=seed,enabled=selection_enabled)
        if method=='ss_single': selected=selected[:1]
    count=len(selected)
    each=dimension if budget=='per_candidate' else 128*(dimension//count//128)
    require(each>=128,'insufficient_total_budget')
    memories=[]
    for rows in selected:
        m,_=fit_banked(rows,each,'candidate-store/'+seed,selected_leaves=rows,cache_slots=0)
        memories.append(m)
    audit.update({'used_candidates':count,'storage_budget_policy':budget,'each_candidate_dimension':each,
                  'used_total_dimension':each*count,'requested_dimension':dimension})
    return MemoryCommittee(memories,audit)

def calibrate_gate(model,rows,*,risk_target=DEFAULT_RISK_TARGET):
    """Fit gate only on separate risk-calibration rows. No statistical guarantee."""
    require(0<=risk_target<=1 and bool(rows),'invalid_calibration_settings')
    answers=[model.predict(c,threshold=0.) for c,_ in rows]
    thresholds=sorted({0.}|{a['confidence'] for a in answers if a['unanimous']})
    trials=[]
    for t in thresholds:
        accepted=[(a,y) for a,(_,y) in zip(answers,rows) if a['unanimous'] and a['confidence']>=t]
        wrong=sum(a['value']!=y for a,y in accepted)
        trials.append({'threshold':t,'accepted':len(accepted),'wrong':wrong,
                       'empirical_risk':wrong/len(accepted) if accepted else None})
    good=[r for r in trials if r['accepted'] and r['empirical_risk']<=risk_target]
    best=max(good,key=lambda r:(r['accepted'],-r['threshold'])) if good else None
    model.threshold=best['threshold'] if best else 1e6
    return {'risk_target':risk_target,'calibration_requests':len(rows),'threshold':model.threshold,'trials':trials,
            'calibration_feasible':best is not None,'statistical_risk_guarantee':False,
            'scope':'Empirical gate on finite calibration data; correlation surplus is not a probability.'}
