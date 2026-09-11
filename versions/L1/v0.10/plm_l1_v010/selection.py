"""Supervised candidate masks, phase recovery plus separate selection validation.

Train weights use training rows only. Validation labels rank/support masks;
they are supervision, not an independent risk guarantee. Enumerating masks,
loss counting, parsimony and truncation are ordinary control operations.
"""
from itertools import combinations
import time
import numpy as np
from .base.selection import unique_rows,grouped,select as legacy_select
from .base.component.algebra import canonical,require,digest
from .base.component.banked import FreshBook,key_code,value_code
from .base.thresholds import MIN_SCORE,MIN_MARGIN
from . import policy

def metrics(predictions,rows):
    n=len(rows); correct=sum(p==y for p,(_,y) in zip(predictions,rows))
    abstained=sum(p is None for p in predictions); wrong=n-correct-abstained
    return {'requests':n,'correct':correct,'wrong':wrong,'abstained':abstained,
            'loss':(wrong+policy.ABSTENTION_LOSS*abstained)/n,'coverage':(n-abstained)/n}

def assess(train,validation,mask,dimension,seed,method,enabled):
    groups=grouped(train,mask); labels=sorted({y for _,y in train})
    probabilities=np.array([[counts[t]/sum(counts.values()) for t in labels] for _,counts in groups])
    queries=train+validation
    identities={canonical({f:c[f] for f in mask}):{f:c[f] for f in mask} for c,_ in queries}
    keys=[identities[k] for k in sorted(identities)]; lookup={canonical(k):i for i,k in enumerate(keys)}
    if method=='symbolic':
        table={canonical(c):p for (c,_),p in zip(groups,probabilities)}
        scores=np.array([table.get(canonical(k),np.zeros(len(labels))) for k in keys])
    else:
        book=FreshBook(dimension,seed)
        k=np.array([key_code(book,c) for c,_ in groups]); v=np.array([value_code(book,y) for y in labels])
        means=probabilities@v
        h=np.einsum('ij,ij->j',k.conj(),means) if enabled else np.zeros(dimension,dtype=np.complex128)
        q=np.array([key_code(book,c) for c in keys])
        scores=(v.conj()@(q*h).T).real.T/dimension
    predicted=[]
    for score in scores:
        order=np.argsort(-score,kind='stable'); top=float(score[order[0]])
        runner=max(0.,float(score[order[1]])) if len(order)>1 else 0.
        predicted.append(labels[int(order[0])] if top>=MIN_SCORE and top-runner>=MIN_MARGIN else None)
    predictions=[predicted[lookup[canonical({f:c[f] for f in mask})]] for c,_ in queries]
    return {'mask':list(mask),'projected_contexts':len(groups),
            'train':metrics(predictions[:len(train)],train),'validation':metrics(predictions[len(train):],validation),
            'estimated_complex_multiplications':0 if method=='symbolic' else dimension*(len(groups)*2+len(keys)*len(labels)),
            'matrix_payload_estimate_bytes':0 if method=='symbolic' else 16*dimension*(4*len(groups)+2*len(keys)+2*len(labels)+1)}

def select_candidates(observations,validation,*,method='ss',dimension=2048,seed='candidate-development-0',enabled=True):
    require(method in ('ss','symbolic') and type(dimension) is int and 128<=dimension<=8192 and dimension%128==0,'invalid_candidate_settings')
    require(type(seed) is str and 0<len(seed)<=80 and type(enabled) is bool,'invalid_candidate_settings')
    started=time.perf_counter(); train=unique_rows(observations); val=unique_rows(validation)
    fields=sorted(train[0][0]); require(set(fields)==set(val[0][0]),'validation_fields_mismatch')
    require(len({canonical(c) for c,_ in train})<=256 and len({canonical(c) for c,_ in val})<=256,'candidate_context_capacity_exceeded')
    labels=sorted({y for _,y in train}); positive_only=len(labels)==1
    masks=[tuple(fields)] if positive_only else [m for n in range(1,len(fields)+1) for m in combinations(fields,n)]
    trials=[assess(train,val,m,dimension,seed,method,enabled) for m in masks]
    usable=[t for t in trials if t['train']['loss']<=policy.MAX_TRAIN_LOSS and t['train']['coverage']>=policy.MIN_TRAIN_COVERAGE]
    if usable:
        best=min(t['train']['loss'] for t in usable)
        usable=[t for t in usable if t['train']['loss']<=best+policy.TRAIN_SLACK]
    if usable:
        best=min(t['validation']['loss'] for t in usable)
        usable=[t for t in usable if t['validation']['loss']<=min(policy.MAX_VALIDATION_LOSS,best+policy.VALIDATION_SLACK)]
    if usable:
        fewest=min(len(t['mask']) for t in usable)
        pool=sorted([t for t in usable if len(t['mask'])==fewest],key=lambda t:(t['validation']['loss'],t['train']['loss'],t['projected_contexts'],canonical(t['mask'])))
    else: pool=[]
    overflow=len(pool)>policy.MAX_CANDIDATES
    selected=pool[:policy.MAX_CANDIDATES] if pool else [next(t for t in trials if t['mask']==fields)]
    leaves=[[({f:c[f] for f in t['mask']},y) for c,y in train] for t in selected]
    audit={'method':method,'dimension':dimension,'seed':seed,'enabled':enabled,'policy':policy.values(),
           'training_observations':len(observations),'unique_training_rows':len(train),'validation_observations':len(validation),'unique_validation_rows':len(val),
           'training_digest':digest(train),'validation_digest':digest(val),'labels':labels,'trials':trials,
           'supported':bool(pool) and not overflow,'overflow':overflow,'retained_count':len(selected),'plausible_minimal_count':len(pool),
           'selected_masks':[t['mask'] for t in selected],
           'status':'candidate_overflow' if overflow else 'supported_minimal_candidates' if pool else 'unsupported_full_context_fallback',
           'positive_only_full_context':positive_only,'wall_seconds':time.perf_counter()-started}
    return leaves,audit
