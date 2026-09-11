import itertools
import random
from ss_online.algebra import canonical,digest


def make_case(seed):
    buckets=[[] for _ in range(4)]
    for vs in itertools.product(range(8),repeat=4):
        c=dict(zip(('f0','f1','f2','f3'),map(str,vs)))
        label=str(int(digest(['online-truth',seed,c])[:8],16)%4)
        buckets[int(label)].append({'context':c,'label':label,'id':digest(['online-key',c])[:20]})
    rng=random.Random(seed)
    for b in buckets:rng.shuffle(b)
    groups={}
    for i,name in enumerate(('A','B','C')):
        rows=[r for b in buckets for r in b[i*16:(i+1)*16]]
        rng.shuffle(rows);groups[name]=rows
    unknown=[r['context'] for b in buckets for r in b[48:]];rng.shuffle(unknown)
    noisy=[];changed=[]
    for y in map(str,range(4)):
        pool=[r for r in groups['A'] if r['label']==y]
        noisy += [r['id'] for r in sorted(pool,key=lambda r:digest(['noise',seed,r['id']]))[:2]]
        changed += [r['id'] for r in sorted(pool,key=lambda r:digest(['drift',seed,r['id']]))[:4]]
    return {'seed':seed,'groups':groups,'unknown':unknown[:128],'noisy_first_A_ids':noisy,'changed_A_ids':changed}


def stream(case,scenario):
    if scenario not in ('clean','noisy_first'):raise ValueError('invalid_scenario')
    blocks=[]
    specs=[(g,str(i),case['groups'][g]) for g in ('A','B','C') for i in range(1,5)]
    specs += [('review_A','1',case['groups']['A'])]
    specs += [('drift',str(i),[r for r in case['groups']['A'] if r['id'] in case['changed_A_ids']]) for i in range(1,5)]
    for phase,epoch,rows in specs:
        order=list(rows);random.Random(digest(['online-order',case['seed'],phase,epoch])).shuffle(order)
        events=[]
        for row in order:
            truth=str((int(row['label'])+1)%4) if phase=='drift' else row['label']
            noisy=scenario=='noisy_first' and phase=='A' and epoch=='1' and row['id'] in case['noisy_first_A_ids']
            teacher=str((int(truth)+1)%4) if noisy else truth
            events.append({'id':row['id'],'context':row['context'],'teacher_label':teacher,'truth':truth,'corrupted':noisy})
        blocks.append({'phase':phase,'epoch':int(epoch),'events':events})
    return blocks


def validate(case):
    rows=[r for group in case['groups'].values() for r in group]
    keys=[canonical(r['context']) for r in rows]
    unknown=[canonical(c) for c in case['unknown']]
    return len(keys)==len(set(keys))==192 and len(unknown)==len(set(unknown))==128 and not set(keys)&set(unknown)
