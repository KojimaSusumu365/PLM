import numpy as np
from plm_l1_v011.portability import compare as compare_base
from .core import POLICIES


def signature(model, context, policy):
    try:
        r = model.predict(context, policy=policy)
    except ValueError as error:
        return ('rejected', str(error))
    evidence = [(e['member'], e['completions'], e['answers'], e['prediction_abstentions'],
                 e['prediction_disagreements'], e['missing_witnesses'], e['conflicting_witnesses']) for e in r['evidence']]
    return (r['status'], r['value'], r['reason'], r['completion_count'], evidence)


def compare(left, right, contexts):
    atol = rtol = 1e-12
    base = compare_base(left.base, right.base, [c for c in contexts if all(v in left.base.config['vocabulary'].get(f, []) for f, v in c.items())])
    metadata = {k: v for k, v in left.meta.items() if k != 'base_fingerprint'} == {k: v for k, v in right.meta.items() if k != 'base_fingerprint'}
    weights = len(left.evidence) == len(right.evidence) and all(a.weights.shape == b.weights.shape and np.allclose(a.weights, b.weights, atol=atol, rtol=rtol) for a, b in zip(left.evidence, right.evidence))
    maximum = max((float(np.max(np.abs(a.weights - b.weights))) if a.weights.size else 0.) for a, b in zip(left.evidence, right.evidence)) if weights else None
    decisions = all(signature(left, c, p) == signature(right, c, p) for c in contexts for p in POLICIES)
    return {'functional_passed': base['functional_passed'] and metadata and weights and decisions,
            'base': base, 'guard_metadata_equal': metadata, 'witness_coefficients_within_tolerance': weights,
            'max_witness_coefficient_difference': maximum, 'atol': atol, 'rtol': rtol,
            'discrete_guard_decisions_equal': decisions, 'context_count': len(contexts), 'policy_probes': len(contexts) * len(POLICIES),
            'strict_fingerprint_equal': left.fingerprint == right.fingerprint, 'linux_execution_performed': False}
