"""Masked coherent L1-basis recovery after P1 unbinding; never uses teacher values.

Old P1's role-specific nuisance projector is NOT a drop-in L1 decoder. Here the
same partial-correlation principle is applied to the fixed L1 state/arity bases.
Observed samples are retained; only erased coordinates get hypothesis completion.
"""
import math
import numpy as np
from plm_l1_v09.component.algebra import require
from plm_l1_v09.thresholds import MIN_SCORE,MIN_MARGIN,MIN_PRESENCE,MAX_RESIDUAL
from ss_partial.contract import STATES,inventory,normalize

MIN_OBSERVED=4096

def recover_masked(model,vector,mask):
    require(isinstance(vector,np.ndarray) and vector.shape==(8192,) and np.isfinite(vector).all(),'partial_vector')
    require(isinstance(mask,np.ndarray) and mask.shape==vector.shape and mask.dtype==bool,'partial_mask')
    require(np.all(vector[~mask]==0),'unobserved_components_must_be_zero')
    nobs=int(mask.sum());require(nobs>=MIN_OBSERVED,'insufficient_observed_components')
    c=model.codec;raw=vector[mask]*math.sqrt(3.);decisions=[]
    def scores(basis):return (basis[:,mask].conj()@raw).real/nobs
    def choose(basis,label):
        s=scores(basis);rank=np.argsort(-s,kind='stable');best=float(s[rank[0]]);gap=best-max(0.,float(s[rank[1]]))
        require(best>=MIN_SCORE and gap>=MIN_MARGIN,'masked_'+label)
        decisions.append({'field':label,'score':round(best,8),'margin':round(gap,8)})
        return int(rank[0])
    n=2+choose(c.base.counts,'count')
    for i in range(n):require(np.vdot(c.base.presence[i][mask],raw).real/nobs>=MIN_PRESENCE,'masked_presence')
    oi=choose(c.base.order_codes[n],'presentation');cells={}
    for key in inventory(n,c.candidates):
        si=choose(c.states[key],'state:'+key);arity=choose(c.arities[key],'arity:'+key)
        s=scores(c.values[key]);rank=np.argsort(-s,kind='stable');chosen=set(map(int,rank[:arity]));outside=max([0.]+[float(s[j]) for j in rank[arity:]])
        if arity:require(float(s[rank[arity-1]])>=MIN_SCORE and float(s[rank[arity-1]])-outside>=MIN_MARGIN,'masked_candidates:'+key)
        require(outside<=1.-MIN_SCORE,'masked_unselected:'+key)
        cells[key]={'state':STATES[si],'candidates':[v for j,v in enumerate(c.choices[key]) if j in chosen]}
    observation=normalize({'count':n,'presentation':c.base.orders[n][oi],'cells':cells},c.candidates)
    hypothesis=c.encode(observation);residual=float(np.linalg.norm(vector[mask]-hypothesis[mask])/np.linalg.norm(hypothesis[mask]))
    require(residual<=MAX_RESIDUAL,'masked_residual_excessive')
    completed=vector.copy();completed[~mask]=hypothesis[~mask]
    packet=model.packet(completed);check=model.recover(packet)
    require(check['status']=='recovered' and check['observation']==observation,'full_L1_postcondition')
    require(np.array_equal(completed[mask],vector[mask]),'observed_samples_changed')
    return packet,{'observed_components':nobs,'filled_coordinates':8192-nobs,'observed_residual':residual,
                   'full_residual':check['residual'],'observed_values_retained_exactly':True,'correlation_decisions':decisions,
                   'hypothesis_completion_not_ground_truth':True}
