import itertools,random
from ss_multicode.algebra import digest
from ss_active.selection import context_id,normalize_pool


def make_case(seed,size):
    assert size in (64,128);buckets=[[] for _ in range(4)]
    for values in itertools.product(range(8),repeat=4):
        c=dict(zip(('f0','f1','f2','f3'),map(str,values)));y=int(digest(['active2-truth',seed,c])[:8],16)%4
        buckets[y].append({'id':context_id(c),'context':c,'label':str(y)})
    rng=random.Random(seed)
    for b in buckets:rng.shuffle(b)
    groups={g:[r for b in buckets for r in b[i*size//4:(i+1)*size//4]] for i,g in enumerate('ABCDE')}
    for group in groups.values():rng.shuffle(group)
    pool=[]
    for g in 'AB':
        for y in list('0123'):
            pool.extend(sorted([r for r in groups[g] if r['label']==y],key=lambda r:digest(['active2-pool',seed,r['id']]))[:size//8])
    changed=[r['id'] for y in list('0123') for r in sorted([r for r in pool if r['label']==y],key=lambda r:digest(['active2-change',seed,r['id']]))[:4]]
    used={r['id'] for group in groups.values() for r in group};unknown=[r['context'] for b in buckets for r in b if r['id'] not in used];rng.shuffle(unknown)
    return {'seed':seed,'size':size,'groups':groups,'pool':normalize_pool([{'id':r['id'],'context':r['context']} for r in pool]),'changed_ids':changed,'unknown':unknown[:128]}


def validate(c):
    g=c['size'];rows=[r for group in c['groups'].values() for r in group];ids={r['id'] for r in rows};unknown={context_id(x) for x in c['unknown']};pool=normalize_pool(c['pool'])
    return len(rows)==len(ids)==5*g and len(unknown)==len(c['unknown'])==128 and not ids&unknown and len(pool)==g and {r['id'] for r in pool}<={r['id'] for k in 'AB' for r in c['groups'][k]} and len(set(c['changed_ids']))==16 and set(c['changed_ids'])<={r['id'] for r in pool}


def teaching(case,groups,passes):
    events=[]
    for g in groups:
        for epoch in range(1,passes+1):
            rows=list(case['groups'][g]);random.Random(digest(['active2-order',case['seed'],case['size'],g,epoch])).shuffle(rows)
            events.extend({'context':r['context'],'label':r['label']} for r in rows)
    return events


def truth_map(case,world):
    if world not in ('stationary','changed_pool16'):raise ValueError('invalid_world')
    truth={r['id']:r['label'] for group in case['groups'].values() for r in group}
    if world=='changed_pool16':
        for key in case['changed_ids']:truth[key]=str((int(truth[key])+1)%4)
    return truth
