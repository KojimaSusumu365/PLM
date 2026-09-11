import math
import numpy as np
from plm_l1_v09.component.algebra import require

NAMES=('bias','score','margin','votes','spread','supported','main_score','main_votes','disagreement',
       'other_score','other_margin','other_votes','other_supported','weak_with_supported_other','both_weak',
       'has_protected','load','three_events')

def signals(recall):
    raw=recall.get('raw',{});r=raw.get(recall.get('selected','protected' if 'protected' in raw else 'main'),{})
    main=raw.get('main',{})
    scores=np.asarray(r.get('scores',[[0.,0.]]),float);means=scores.mean(axis=0)
    spread=float(scores[:,int(np.argmax(means))].std())
    clip=lambda x:float(np.clip(x,-1.,1.))
    return {'score':clip(r.get('score',0.)/2),'margin':clip(r.get('margin',0.)/2),'votes':r.get('votes',0)/4,
            'spread':clip(spread/2),'supported':float(recall.get('value') is not None),
            'main_score':clip(main.get('score',0.)/2),'main_votes':main.get('votes',0)/4,
            'disagreement':float(recall.get('status')=='memory_disagreement')}

def extract(recall,other,memory,count):
    a=signals(recall);b=signals(other);x={'bias':1.,**a,
        **{'other_'+k:b[k] for k in ('score','margin','votes','supported')},
        'weak_with_supported_other':(1-a['supported'])*b['supported'],
        'both_weak':(1-a['supported'])*(1-b['supported']),
        'has_protected':float('protected' in memory.ss.parts),
        'load':min(1.,math.log1p(len(memory.ss.parts['main'].registry))/math.log1p(1024)),
        'three_events':float(count==3)}
    validate(x);return {k:float(x[k]) for k in NAMES}

def validate(features):
    require(type(features) is dict and set(features)==set(NAMES),'selector_feature_inventory')
    require(all(type(v) in (float,int) and math.isfinite(v) and -1.<=v<=1. for v in features.values()),'bounded_selector_features')
