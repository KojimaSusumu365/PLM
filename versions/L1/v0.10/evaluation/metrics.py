"""Evaluation-only selective risk, coverage and gold-blind equal-count comparison."""
import hashlib
from plm_l1_v010.base.component.algebra import canonical

def score(predictions,gold):
    if len(predictions)!=len(gold): raise ValueError('prediction_count_mismatch')
    n=len(gold); correct=sum(a==b for a,b in zip(predictions,gold)); absent=sum(a is None for a in predictions)
    wrong=n-correct-absent; accepted=n-absent
    return {'requests':n,'correct':correct,'wrong':wrong,'abstained':absent,'accepted':accepted,
            'coverage':accepted/n if n else None,'selective_risk':wrong/accepted if accepted else None}

def equal_count(rows,predictions):
    """Descriptive only: hashes, never gold, break ties/subsample accepted answers."""
    minimum=min(sum(p is not None for p in ps) for ps in predictions.values())
    result={}
    for name,ps in predictions.items():
        indices=[i for i,p in enumerate(ps) if p is not None]
        indices.sort(key=lambda i:hashlib.sha256(canonical(['v010-matched-count',rows[i]['context']]).encode('utf-8')).hexdigest())
        chosen=indices[:minimum]; gold=[rows[i]['label'] for i in chosen]
        result[name]=score([ps[i] for i in chosen],gold)
    return {'accepted_per_method':minimum,'original_requests':len(rows),'metrics':result,
            'status':'no_positive_common_coverage' if minimum==0 else 'descriptive_gold_blind_subsample',
            'scope':'Same number answered, not the same inputs and not a deployed threshold tuned on test labels.'}

def curves(answers,gold):
    thresholds=(0.,.05,.10,.20,.30,.50)
    return [{'threshold':t,**score([a['value'] if a['unanimous'] and a['confidence']>=t else None for a in answers],gold)} for t in thresholds]
