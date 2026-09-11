import itertools,time
import numpy as np
from .algebra import Book,BatchFeatures,terms,digest,require
from .core import Model,rows_checked,winner,loss,counts_for,exact_scores,MAX_CANDIDATES,MAX_SELECTION_LOSS,MIN_MARGIN

def fit(train,validation,*,representation='additive',selector='off',backend='ss',dimension=2048,seed='development-0',budget='per_candidate',enabled=True):
    started=time.perf_counter();fields=rows_checked(train);rows_checked(validation,fields)
    require(representation in ('additive','product','hybrid3') and selector in ('off','validation') and backend in ('ss','exact'),'invalid_method')
    require(type(dimension) is int and 512<=dimension<=8192 and dimension%128==0,'invalid_dimension')
    require(type(seed) is str and 0<len(seed)<=80 and budget in ('per_candidate','fixed_total') and type(enabled) is bool,'invalid_settings')
    labels=sorted({r['label'] for r in train});require(2<=len(labels)<=16,'label_count_out_of_scope')
    vocabulary={f:sorted({r['context'][f] for r in train}) for f in fields}
    require(all(v in vocabulary[f] for r in validation for f,v in r['context'].items()),'unknown_validation_value')
    contexts=[r['context'] for r in train+validation];n=len(train);book=Book(dimension,seed);batch=BatchFeatures(contexts,book) if backend=='ss' else None
    masks=[tuple(fields)] if selector=='off' else [m for k in range(1,len(fields)+1) for m in itertools.combinations(fields,k)]
    trials=[]
    for mask in masks:
        if backend=='ss':
            x=batch.matrix(mask,representation);w=np.array([x[:n][[r['label']==y for r in train]].mean(axis=0) for y in labels])
            scores=(x@w.conj().T).real/dimension if enabled else np.zeros((len(contexts),len(labels)))
        else:
            counts,cc=counts_for(train,mask,representation,labels);scores=exact_scores(contexts,mask,representation,counts,cc)
        predicted=[winner(s,labels)[0] for s in scores]
        trials.append({'mask':list(mask),'train_loss':loss(predicted[:n],train),'validation_loss':loss(predicted[n:],validation),'terms':len(terms(mask,representation))})
    if selector=='validation':
        good=[r for r in trials if r['train_loss']<=MAX_SELECTION_LOSS and r['validation_loss']<=MAX_SELECTION_LOSS]
        if good:
            best=min(r['validation_loss'] for r in good);good=[r for r in good if r['validation_loss']==best]
            smallest=min(len(r['mask']) for r in good);pool=[r for r in good if len(r['mask'])==smallest]
        else:pool=[]
        selected=pool[:MAX_CANDIDATES] if pool else [trials[-1]];supported=bool(pool) and len(pool)<=MAX_CANDIDATES
    else:pool=trials;selected=trials;supported=True
    if not enabled and backend=='ss':supported=False
    each=dimension if budget=='per_candidate' else 128*(dimension//len(selected)//128)
    members=[]
    for trial in selected:
        mask=trial['mask'];counts,cc=counts_for(train,mask,representation,labels)
        if backend=='ss':
            b=Book(each,seed);x=np.array([b.vector(r['context'],mask,representation)[0] for r in train])
            w=np.array([x[[r['label']==y for r in train]].mean(axis=0) for y in labels])
            if not enabled:w[:]=0
            counts={}
        else:w=np.zeros((0,0),dtype=np.complex128)
        members.append({'mask':mask,'dimension':each if backend=='ss' else 0,'weights':w,'counts':counts,'class_counts':cc})
    config={'representation':representation,'selector':selector,'backend':backend,'requested_dimension':dimension if backend=='ss' else None,
            'seed':seed if backend=='ss' else 'exact-kernel','budget':budget,'fields':fields,'vocabulary':vocabulary,'labels':labels,
            'min_margin':MIN_MARGIN,'max_candidates':MAX_CANDIDATES,'max_selection_loss':MAX_SELECTION_LOSS,'max_interaction_order':3}
    training={'rows':len(train),'selection_rows_used':len(validation) if selector=='validation' else 0,'train_digest':digest(train),
              'selection_digest':digest(validation) if selector=='validation' else None,'supported':supported,'plausible_masks':len(pool),
              'overflow':len(pool)>MAX_CANDIDATES,'weights_use_training_only':True,'no_online_learning':True,'phase_enabled':enabled}
    model=Model(config,members,training)
    audit={'trials':trials,'selected_masks':[m['mask'] for m in members],'supported':supported,'plausible_masks':len(pool),
           'selection_dimension':dimension if backend=='ss' else None,'compiled_dimensions':[m['dimension'] for m in members]}
    performance={'fit_seconds':time.perf_counter()-started,'training_term_cache_bytes':batch.payload() if batch else 0,
                 'estimated_term_complex_multiplications':batch.multiplies if batch else 0,'estimated_bundle_complex_additions':batch.additions if batch else 0,
                 'cost_counter_scope':'Term generation during selection only; excludes scoring BLAS, final refit, allocation and Python control.'}
    return model,audit,performance

def calibrate(model,rows,risk_target=.1):
    rows_checked(rows,model.config['fields']);require(0<=risk_target<=1,'invalid_risk_target')
    predictions=[model.predict(r['context'],threshold=0.) for r in rows]
    thresholds=sorted({0.}|{p['confidence'] for p in predictions if p['value'] is not None});trials=[]
    for t in thresholds:
        accepted=[(p,r) for p,r in zip(predictions,rows) if p['value'] is not None and p['confidence']>=t]
        wrong=sum(p['value']!=r['label'] for p,r in accepted)
        trials.append({'threshold':t,'accepted':len(accepted),'wrong':wrong,'risk':wrong/len(accepted) if accepted else None})
    feasible=[r for r in trials if r['accepted'] and r['risk']<=risk_target]
    chosen=max(feasible,key=lambda r:(r['accepted'],-r['threshold'])) if feasible else None
    model.threshold=chosen['threshold'] if chosen else 1e6
    model.calibration={'rows':len(rows),'digest':digest(rows),'risk_target':risk_target,'feasible':chosen is not None,'trials':trials,'statistical_guarantee':False,'scope':'Complete clean calibration inputs only; not recalibrated for erased fields, numeric masks or shifts.'}
    model.refresh();return model.calibration
