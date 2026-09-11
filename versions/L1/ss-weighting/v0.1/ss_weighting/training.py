"""Training and v0.13 adapter; prediction stays in unchanged v0.13 core."""
import json
import numpy as np
from plm_l1_v013.algebra import Book, canonical, digest
from plm_l1_v013.training import fit as legacy_fit
from .learning import learn, METHODS
from .memory import Memory, vectors


def checked(rows):
    if type(rows) is not list or not 2 <= len(rows) <= 4096:
        raise ValueError('invalid_rows')
    if any(type(r) is not dict or set(r) != {'context', 'label'} or type(r['context']) is not dict for r in rows):
        raise ValueError('teacher_schema')
    groups = {}
    fields = sorted(rows[0]['context'])
    for r in rows:
        if type(r) is not dict or set(r) != {'context', 'label'} or type(r['label']) is not str:
            raise ValueError('teacher_schema')
        c = r['context']
        if type(c) is not dict or sorted(c) != fields or not fields or not all(type(v) is str for v in c.values()):
            raise ValueError('teacher_context')
        k = canonical(c)
        if k in groups and groups[k]['label'] != r['label']:
            raise ValueError('conflicting_teacher')
        groups[k] = r
    unique = [groups[k] for k in sorted(groups)]
    labels = sorted({r['label'] for r in unique})
    if not 2 <= len(labels) <= 16:
        raise ValueError('label_scope')
    return unique, fields, labels


def fit(rows, *, dimension=128, seed='weight-unit', method='uniform', backend='ss'):
    unique, fields, labels = checked(rows)
    if backend not in ('ss', 'exact') or method not in METHODS or type(dimension) is not int or not 8 <= dimension <= 4096:
        raise ValueError('invalid_settings')
    meta = {'schema': 'plm-ss-weighting-experiment-01', 'backend': backend,
            'dimension': dimension if backend == 'ss' else 0, 'seed': seed if backend == 'ss' else 'exact',
            'method': method, 'fields': fields, 'labels': labels, 'threshold': 0.5,
            'entries': {}, 'teachers_digest': digest(unique), 'known_keys': len(unique), 'eligible_for_inference': False}
    if backend == 'exact':
        # With identity kernel, both regularized objectives have B=T at optimum.
        if method == 'gain2':
            raise ValueError('gain_control_is_ss_only')
        meta['entries'] = {canonical(r['context']): r['label'] for r in unique}
        return Memory(meta, np.zeros((0, 0), dtype=np.complex128)), {'method': method, 'identity_kernel_solution': 'B=T', 'known_keys': len(unique)}
    book = Book(dimension, seed)
    b = vectors(book, [r['context'] for r in unique], fields)
    target = np.array([[int(y == r['label']) for y in labels] for r in unique], dtype=float)
    w, audit = learn(b, target, method)
    return Memory(meta, w), audit


def fit_structured(rows, *, dimension=512, seed='evaluation-0', method='uniform', backend='ss'):
    if method not in METHODS or method == 'gain2':
        raise ValueError('invalid_structured_method')
    model, selection, cost = legacy_fit(rows, dimension=dimension, seed=seed, backend=backend, retention='all')
    audits = []
    if backend == 'ss' and method != 'uniform':
        for member in model.members:
            mask = member['mask']
            observed = {}
            for row in rows:
                context = {f: row['context'][f] for f in mask}
                observed[canonical(context)] = (context, row['label'])
            records = [observed[k] for k in sorted(observed)]
            b = vectors(model.book, [c for c, _ in records], mask)
            target = np.array([[int(y == label) for y in model.config['labels']] for _, label in records], dtype=float)
            member['weights'], audit = learn(b, target, method)
            audits.append(dict(mask=mask, **audit))
    model.training['experimental_weighting'] = {'version': '0.1', 'method': method, 'candidate_and_acceptance_control': 'unchanged v0.13',
                                               'online_teacher_session_integrated': False}
    model.refresh()
    return model, audits
