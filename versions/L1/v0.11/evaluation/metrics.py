import hashlib,json

def measure(predictions,allowed):
    assert len(predictions)==len(allowed)
    n=len(allowed);accepted=sum(p is not None for p in predictions)
    correct=sum(len(a)==1 and p==a[0] for p,a in zip(predictions,allowed));wrong=accepted-correct
    ambiguous=sum(len(a)>1 for a in allowed);unsafe=sum(p is not None and len(a)>1 for p,a in zip(predictions,allowed))
    identifiable=sum(len(a)==1 for a in allowed)
    return {'requests':n,'correct':correct,'wrong':wrong,'abstained':n-accepted,'accepted':accepted,'coverage':accepted/n if n else None,
            'selective_risk':wrong/accepted if accepted else None,'ambiguous_requests':ambiguous,'unsafe_confirmations':unsafe,
            'identifiable_requests':identifiable,'identifiable_correct':correct,'unsupported_requests':sum(not a for a in allowed),
            'identifiable_abstained':sum(p is None and len(a)==1 for p,a in zip(predictions,allowed)),
            'ambiguous_correctly_abstained':ambiguous-unsafe,
            'compatible_but_unjustified':sum(p is not None and len(a)>1 and p in a for p,a in zip(predictions,allowed))}

def equal_count(rows):
    n=min(sum(p['gated'] is not None for p in r['predictions']) for r in rows)
    metrics={}
    for r in rows:
        ps=[p for p in r['predictions'] if p['gated'] is not None]
        ps.sort(key=lambda p:hashlib.sha256(json.dumps(p['query_id'],sort_keys=True).encode()).hexdigest());ps=ps[:n]
        metrics[r['method']]=measure([p['gated'] for p in ps],[p['allowed'] for p in ps])
    return {'accepted_per_method':n,'status':'no_positive_common_coverage' if not n else 'descriptive_equal_count',
            'metrics':metrics,'scope':'Gold-blind same number answered, not the same inputs or a deployed threshold.'}
