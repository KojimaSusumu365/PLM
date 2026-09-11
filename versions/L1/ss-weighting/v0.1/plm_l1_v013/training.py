"""Exact training consistency chooses masks; inference can use SS or exact recall."""
import itertools
import time
import numpy as np
from .algebra import Book, canonical, digest, require
from .core import Model, key, MAX_FIELDS, MAX_ORDER, SUPPORT_THRESHOLD


def rows_checked(rows):
    require(type(rows) is list and 2 <= len(rows) <= 4096, 'invalid_teachers')
    for row in rows:
        require(type(row) is dict and set(row) == {'context', 'label'}, 'unexpected_teacher_fields')
        c = row['context']
        require(type(c) is dict and 1 <= len(c) <= MAX_FIELDS and all(type(f) is str and 0 < len(f) <= 64 and type(v) is str and 0 < len(v) <= 64 for f, v in c.items()), 'invalid_teacher_context')
        require(type(row['label']) is str and 0 < len(row['label']) <= 128, 'invalid_teacher_label')
    fields = sorted(rows[0]['context'])
    require(all(sorted(r['context']) == fields for r in rows), 'teacher_fields_mismatch')
    return fields


def fit(rows, *, backend='ss', dimension=2048, seed='evaluation-0', retention='all', max_order=MAX_ORDER):
    start = time.perf_counter()
    fields = rows_checked(rows)
    require(backend in ('ss', 'exact') and retention in ('all', 'minimal'), 'invalid_method')
    require(type(dimension) is int and 128 <= dimension <= 4096 and dimension % 128 == 0, 'invalid_dimension')
    require(type(max_order) is int and 1 <= max_order <= MAX_ORDER and type(seed) is str and 0 < len(seed) <= 80, 'invalid_settings')
    labels = sorted({r['label'] for r in rows})
    require(2 <= len(labels) <= 16, 'label_inventory_out_of_scope')
    vocabulary = {f: sorted({r['context'][f] for r in rows}) for f in fields}
    require(all(len(v) <= 2 for v in vocabulary.values()), 'binary_feature_inventory_required')
    d = dimension if backend == 'ss' else 0
    code_seed = seed if backend == 'ss' else 'exact'
    book = Book(d, 'v013-witness/' + code_seed)
    candidates = []
    audit = []
    for order in range(1, min(max_order, len(fields)) + 1):
        for mask in itertools.combinations(fields, order):
            groups = {}
            for row in rows:
                k = key(row['context'], mask)
                groups.setdefault(k, set()).add(row['label'])
            conflicts = sum(len(v) > 1 for v in groups.values())
            audit.append({'mask': list(mask), 'conflicting_keys': conflicts, 'known_keys': len(groups)})
            if not conflicts:
                candidates.append((list(mask), groups))
    if retention == 'minimal' and candidates:
        size = min(len(m) for m, _ in candidates)
        candidates = [(m, g) for m, g in candidates if len(m) == size]
    members = []
    import json
    for mask, groups in candidates:
        entries = {}
        weights = np.zeros((len(labels), d), dtype=np.complex128) if backend == 'ss' else np.zeros((0, 0), dtype=np.complex128)
        for k, ys in sorted(groups.items()):
            y = next(iter(ys))
            counts = [int(label == y) for label in labels]
            entries[k] = counts
            if backend == 'ss':
                context = dict(zip(mask, json.loads(k)))
                vector, _ = book.vector(context, mask, 'product')
                weights[labels.index(y)] += vector
        members.append({'mask': mask, 'known_keys': len(groups), 'total_keys': int(np.prod([len(vocabulary[f]) for f in mask])),
                        'entries': entries if backend == 'exact' else {}, 'weights': weights})
    config = {'fields': fields, 'vocabulary': vocabulary, 'labels': labels, 'backend': backend, 'dimension': d,
              'seed': code_seed, 'retention': retention, 'max_order': max_order, 'support_threshold': SUPPORT_THRESHOLD}
    training = {'rows': len(rows), 'unique_contexts': len({canonical(r['context']) for r in rows}), 'digest': digest(rows),
                'mask_selection': 'All exact teacher-consistent masks up to fixed order; optional smallest-order ablation.',
                'ss_runtime_has_training_key_table': False, 'unobserved_cell_means_unknown': True}
    model = Model(config, members, training)
    return model, {'trials': audit, 'retained_masks': [m['mask'] for m in members]}, {'fit_seconds': time.perf_counter() - start}
