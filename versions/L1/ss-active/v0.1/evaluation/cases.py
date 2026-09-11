import itertools
import random
from ss_multicode.algebra import digest, canonical
from ss_active.selection import context_id, normalize_pool


def make_case(seed, size):
    assert size in (64, 128)
    buckets = [[] for _ in range(4)]
    for vs in itertools.product(range(8), repeat=4):
        c = dict(zip(('f0', 'f1', 'f2', 'f3'), map(str, vs)))
        y = int(digest(['active-truth', seed, c])[:8], 16) % 4
        buckets[y].append({'id': context_id(c), 'context': c, 'label': str(y)})
    rng = random.Random(seed)
    for b in buckets: rng.shuffle(b)
    groups = {g: [r for b in buckets for r in b[i*size//4:(i+1)*size//4]] for i, g in enumerate('ABCD')}
    for group in groups.values(): rng.shuffle(group)
    pool_rows = []
    for group in ('A', 'B'):
        for y in list('0123'):
            candidates = [r for r in groups[group] if r['label'] == y]
            pool_rows.extend(sorted(candidates, key=lambda r: digest(['active-pool', seed, r['id']]))[:size//8])
    changed = [r['id'] for y in list('0123') for r in sorted([r for r in pool_rows if r['label'] == y], key=lambda r: digest(['active-change', seed, r['id']]))[:4]]
    used = {r['id'] for g in groups.values() for r in g}
    unknown = [r['context'] for b in buckets for r in b if r['id'] not in used]; rng.shuffle(unknown)
    return {'seed': seed, 'size': size, 'groups': groups, 'pool': normalize_pool([{'id': r['id'], 'context': r['context']} for r in pool_rows]),
            'changed_ids': changed, 'unknown': unknown[:128]}


def validate(case):
    rows = [r for g in case['groups'].values() for r in g]
    ids = {r['id'] for r in rows}; pool = normalize_pool(case['pool']); old = {r['id'] for g in ('A', 'B') for r in case['groups'][g]}
    unknown = [context_id(c) for c in case['unknown']]
    return (len(rows) == len(ids) == case['size']*4 and len(unknown) == len(set(unknown)) == 128 and not ids & set(unknown)
            and len(pool) == case['size'] and {r['id'] for r in pool} <= old
            and len(set(case['changed_ids'])) == 16 and set(case['changed_ids']) <= {r['id'] for r in pool})


def teaching(case, groups, passes):
    events = []
    for g in groups:
        for epoch in range(1, passes+1):
            rows = list(case['groups'][g]); random.Random(digest(['active-order', case['seed'], case['size'], g, epoch])).shuffle(rows)
            events.extend({'id': r['id'], 'context': r['context'], 'label': r['label'], 'phase': g, 'epoch': epoch} for r in rows)
    return events


def truth_map(case, scenario):
    if scenario not in ('stationary', 'changed_pool16'): raise ValueError('scenario')
    truth = {r['id']: r['label'] for g in case['groups'].values() for r in g}
    if scenario == 'changed_pool16':
        for key in case['changed_ids']: truth[key] = str((int(truth[key])+1) % 4)
    return truth
