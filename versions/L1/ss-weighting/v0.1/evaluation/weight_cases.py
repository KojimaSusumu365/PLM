import itertools
import random
from plm_l1_v013.algebra import canonical, digest


def memory_case(seed, count, unknown_count=256):
    contexts = [dict(zip(('f0', 'f1', 'f2', 'f3'), map(str, vs))) for vs in itertools.product(range(8), repeat=4)]
    # Each class contributes exactly count/4 teacher keys; labels are evaluator-generated.
    buckets = [[] for _ in range(4)]
    for c in contexts:
        y = int(digest(['weight-truth', seed, c])[:8], 16) % 4
        buckets[y].append({'context': c, 'label': str(y)})
    rng = random.Random(seed)
    for b in buckets:
        rng.shuffle(b)
    teachers = [r for b in buckets for r in b[:count // 4]]
    rng.shuffle(teachers)
    used = {canonical(r['context']) for r in teachers}
    unknown = [c for c in contexts if canonical(c) not in used]
    rng.shuffle(unknown)
    return {'seed': seed, 'teachers': teachers, 'unknown': unknown[:unknown_count]}
