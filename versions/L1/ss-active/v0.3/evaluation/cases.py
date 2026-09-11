"""Artificial cases. v0.2 construction, new v0.3 seeds; drift challenge is new."""
import itertools
import random
from ss_multicode.algebra import digest
from ss_trace.runtime import context_id


def make_case(seed, size):
    buckets = [[] for _ in range(4)]
    for values in itertools.product(range(8), repeat=4):
        c = dict(zip(('f0','f1','f2','f3'), map(str, values)))
        y = int(digest(['active2-truth', seed, c])[:8], 16)%4
        buckets[y].append({'id': context_id(c), 'context': c, 'label': str(y)})
    rng = random.Random(seed)
    for b in buckets: rng.shuffle(b)
    groups = {g: [r for b in buckets for r in b[i*size//4:(i+1)*size//4]] for i,g in enumerate('ABCDE')}
    for rows in groups.values(): rng.shuffle(rows)
    pool = []
    for g in 'AB':
        for y in '0123':
            pool.extend(sorted([r for r in groups[g] if r['label']==y], key=lambda r: digest(['active2-pool',seed,r['id']]))[:size//8])
    used = {r['id'] for rows in groups.values() for r in rows}
    unknown = [r['context'] for b in buckets for r in b if r['id'] not in used]; rng.shuffle(unknown)
    return {'seed': seed, 'size': size, 'groups': groups,
            'pool': sorted([{'id': r['id'], 'context': r['context']} for r in pool], key=lambda r:r['id']),
            'unknown': unknown[:128]}


def teaching(case, groups, passes):
    events = []
    for g in groups:
        for epoch in range(1, passes+1):
            rows = list(case['groups'][g])
            random.Random(digest(['active2-order',case['seed'],case['size'],g,epoch])).shuffle(rows)
            events.extend({'context': r['context'], 'label': r['label']} for r in rows)
    return events


def probes(case):
    rows = [r for g in 'ABCDE' for r in case['groups'][g]]
    return rows + [{'id': context_id(c), 'context': c, 'label': None} for c in case['unknown']]
