"""Global-mask selection by empirical phase recovery, with explicit ordinary search.

Enumeration, grouping, supervised scoring and complexity preference are ordinary
control. SS trials actually construct H and correlate queries; no entropy or
symbolic purity test decides their admissibility. ID3 is an optional comparator.
"""
from collections import Counter
from itertools import combinations
import time
import numpy as np
from .component.algebra import canonical, require
from .component.banked import FreshBook, key_code, value_code
from .thresholds import MIN_SCORE, MIN_MARGIN, SELECTION_REQUIRED_ACCURACY

METHODS = ('ss', 'symbolic', 'id3', 'full')


def unique_rows(observations):
    require(type(observations) is list and 0 < len(observations) <= 20000, 'invalid_observations')
    require(all(type(r) in (list,tuple) and len(r)==2 and type(r[0]) is dict for r in observations), 'invalid_observation')
    fields = set(observations[0][0])
    require(0 < len(fields) <= 6 and all(type(f) is str for f in fields), 'invalid_feature_inventory')
    unique = {}
    for context, label in observations:
        require(type(context) is dict and set(context) == fields and type(label) is str, 'invalid_observation')
        unique[canonical([context, label])] = (context, label)
    return [unique[k] for k in sorted(unique)]


def grouped(rows, mask):
    groups = {}
    for context, label in rows:
        key = {f: context[f] for f in mask}
        identity = canonical(key)
        if identity not in groups:
            groups[identity] = [key, Counter()]
        groups[identity][1][label] += 1
    return [groups[k] for k in sorted(groups)]


def trial(rows, mask, labels, dimension, seed, *, symbolic=False, enabled=True):
    groups = grouped(rows, mask)
    probabilities = np.array([[counts[t] / sum(counts.values()) for t in labels] for _, counts in groups])
    multiplications = matrix_bytes = 0
    if symbolic:
        scores = probabilities
    else:
        book = FreshBook(dimension, seed)
        keys = np.array([key_code(book, key) for key, _ in groups])
        targets = np.array([value_code(book, t) for t in labels])
        means = probabilities @ targets
        weights = np.einsum('ij,ij->j', keys.conj(), means) if enabled else np.zeros(dimension, dtype=np.complex128)
        scores = (targets.conj() @ (keys * weights).T).real.T / dimension
        multiplications = dimension * len(groups) * (2 + len(labels))
        matrix_bytes = 16 * dimension * (4 * len(groups) + 2 * len(labels) + 1)
    correct = wrong = abstained = 0
    true_scores, true_margins = [], []
    for (_, counts), score in zip(groups, scores):
        order = np.argsort(-score, kind='stable')
        top = float(score[order[0]])
        runner = max(0., float(score[order[1]])) if len(order) > 1 else 0.
        accepted = top >= MIN_SCORE and top - runner >= MIN_MARGIN
        chosen = labels[int(order[0])] if accepted else None
        for i, label in enumerate(labels):
            n = counts[label]
            if not n:
                continue
            correct += n * (chosen == label)
            wrong += n * (accepted and chosen != label)
            abstained += n * (not accepted)
            other = max(0., max((float(score[j]) for j in range(len(labels)) if j != i), default=0.))
            true_scores.append(float(score[i])); true_margins.append(float(score[i]) - other)
    return {'mask': list(mask), 'projected_contexts': len(groups), 'requests': len(rows),
            'correct': int(correct), 'wrong': int(wrong), 'abstained': int(abstained),
            'eligible': correct / len(rows) >= SELECTION_REQUIRED_ACCURACY,
            'minimum_true_score': round(min(true_scores), 8), 'minimum_true_margin': round(min(true_margins), 8),
            'matrix_payload_upper_estimate_bytes': matrix_bytes,
            'estimated_complex_multiplications': multiplications}


def select(observations, *, method='ss', dimension=2048, seed='selection-development-0', enabled=True):
    require(method in METHODS and type(dimension) is int and 128 <= dimension <= 8192 and dimension % 128 == 0, 'invalid_selector_settings')
    require(type(seed) is str and 0 < len(seed) <= 80 and type(enabled) is bool, 'invalid_selector_settings')
    started = time.perf_counter()
    rows = unique_rows(observations); fields = sorted(rows[0][0]); labels = sorted({t for _, t in rows})
    audit = {'method': method, 'dimension': dimension, 'seed': seed, 'enabled': enabled,
             'observations': len(observations), 'unique_context_label_pairs': len(rows),
             'fields': fields, 'candidates': labels, 'trials': [], 'fallback_full_context': False,
             'ordinary_operations': ['candidate enumeration', 'deduplication and grouping', 'supervised scoring', 'complexity ordering', 'full-context fallback'],
             'score_operation': 'phase construction and correlation' if method == 'ss' else method}
    if method == 'id3':
        from .component.projection import dependency_leaves
        leaves = dependency_leaves(rows, True)
        audit['selection_status'] = 'symbolic_id3'
    elif method == 'full' or len(labels) == 1:
        # Positive-only support is not evidence for universal support on unseen keys.
        leaves = rows
        audit['selection_status'] = 'full_context' if method == 'full' else 'positive_only_full_context'
    else:
        for count in range(1, len(fields) + 1):
            for mask in combinations(fields, count):
                audit['trials'].append(trial(rows, mask, labels, dimension, seed, symbolic=method == 'symbolic', enabled=enabled))
        eligible = [r for r in audit['trials'] if r['eligible']]
        if eligible:
            best = min(eligible, key=lambda r: (len(r['mask']), r['projected_contexts'], canonical(r['mask'])))
            mask = best['mask']; audit['selection_status'] = 'empirical_supported_projection'
        else:
            mask = fields; audit['fallback_full_context'] = True
            audit['selection_status'] = 'no_empirically_supported_projection'
        leaves = [({f: context[f] for f in mask}, label) for context, label in rows]
    audit['selected_masks'] = sorted({tuple(sorted(c)) for c, _ in leaves})
    audit['selected_contexts'] = len({canonical(c) for c, _ in leaves})
    audit['estimated_complex_multiplications'] = sum(r['estimated_complex_multiplications'] for r in audit['trials'])
    audit['matrix_payload_upper_estimate_bytes'] = max((r['matrix_payload_upper_estimate_bytes'] for r in audit['trials']), default=0)
    audit['wall_seconds'] = time.perf_counter() - started
    return leaves, audit
