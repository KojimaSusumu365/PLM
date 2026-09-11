import numpy as np


def signature(predictions):
    fields = ('status', 'value', 'possible_labels', 'reason', 'input_insufficient', 'learning_insufficient',
              'candidate_count', 'unknown_cells', 'conflicting_cells', 'dependency_disagreement', 'completion_count', 'eligible_for_inference')
    return [tuple(p[k] for k in fields) for p in predictions]


def compare(a, b, contexts, pool):
    metadata = a.meta == b.meta
    arrays = len(a.members) == len(b.members)
    maximum = 0.
    for x, y in zip(a.members, b.members):
        u, v = x['weights'], y['weights']
        if u.shape != v.shape:
            arrays = False
            continue
        if u.size:
            maximum = max(maximum, float(np.max(np.abs(u - v))))
        arrays &= bool(np.allclose(u, v, atol=1e-12, rtol=1e-12))
    predictions = signature(a.predict_many(contexts)) == signature(b.predict_many(contexts))
    requests = []
    for strategy in ('active', 'random'):
        x, y = a.select(pool, strategy), b.select(pool, strategy)
        requests.append({k: v for k, v in x.items() if k not in ('model_fingerprint', 'diagnostics')} == {k: v for k, v in y.items() if k not in ('model_fingerprint', 'diagnostics')})
    return {'functional_passed': bool(metadata and arrays and predictions and all(requests)), 'metadata_equal': metadata,
            'coefficients_within_tolerance': bool(arrays), 'max_coefficient_difference': maximum, 'atol': 1e-12, 'rtol': 1e-12,
            'discrete_predictions_equal': predictions, 'contexts': len(contexts), 'selected_queries_equal': all(requests),
            'strict_fingerprint_equal': a.fingerprint == b.fingerprint, 'linux_execution_performed': False}
