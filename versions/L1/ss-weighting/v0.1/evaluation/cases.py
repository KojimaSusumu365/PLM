import copy
import itertools
import json
import random
from pathlib import Path
from .legacy_tasks import make_task
from plm_l1_v013.algebra import canonical, digest
ROOT = Path(__file__).resolve().parents[1]


def pack(task_id, family, initial, pool, test, truth):
    # Candidate IDs are hashes of contexts, never labels or their semantic order.
    unlabeled = [{'id': digest(['v013-pool', r['context']])[:20], 'context': r['context']} for r in pool]
    return {'id': task_id, 'family': family, 'initial': initial, 'pool': unlabeled,
            'teacher_answers': {p['id']: r['label'] for p, r in zip(unlabeled, pool)},
            'test': test, 'completion_oracle': truth,
            'scope': 'Only initial labels and requested pool answers reach the learner. Held-out test labels and complete truth remain in evaluator.'}


def paired(split):
    rng = random.Random('v013-pair/' + split)
    fields = list('abcdef')
    rng.shuffle(fields)
    groups = []
    for a, b, c in itertools.product((0, 1), repeat=3):
        noise = list(itertools.product((0, 1), repeat=3))
        rng.shuffle(noise)
        groups.append([{'context': dict(zip(fields, map(str, (a, b, c) + n))), 'label': str(a)} for n in noise])
    worlds = []
    for world in ('simple', 'hidden'):
        g = copy.deepcopy(groups)
        if world == 'hidden':
            for row in g[7]:
                row['label'] = '0'
        worlds.append(pack(f'{split}/paired/{world}', 'paired_' + world,
                           [r for rows in g[:7] for r in rows[:3]],
                           [r for rows in g[:7] for r in rows[3:5]] + g[7][:2],
                           [r for rows in g[:7] for r in rows[5:]] + g[7][2:],
                           [r for rows in g for r in rows]))
    return worlds


def outside(split, rep):
    rng = random.Random(f'v013-outside/{split}/{rep}')
    fields = list('abcdef')
    rng.shuffle(fields)
    groups = []
    for a, b, c in itertools.product((0, 1), repeat=3):
        noise = list(itertools.product((0, 1), repeat=3))
        rng.shuffle(noise)
        groups.append([{'context': dict(zip(fields, map(str, (a, b, c) + n))), 'label': str(a ^ b ^ c ^ n[0])} for n in noise])
    return pack(f'{split}/outside_order4/{rep}', 'outside_order4',
                [r for rows in groups for r in rows[:3]], [r for rows in groups for r in rows[3:5]],
                [r for rows in groups for r in rows[5:]], [r for rows in groups for r in rows])


def tasks(split):
    result = []
    for family in ('unary', 'xor2', 'and2', 'switch3', 'parity3', 'roles', 'polarity_modality'):
        for rep in range(2 if family not in ('roles', 'polarity_modality') else 1):
            old = make_task('v013-' + split, family, rep)
            result.append(pack(f'{split}/{family}/{rep}', family, old['train'], old['selection'],
                               old['calibration'] + old['test'], old['completion_oracle']))
    return result + paired(split) + [outside(split, r) for r in range(2)]


def disjoint(task):
    groups = [{canonical(r['context']) for r in task[n]} for n in ('initial', 'pool', 'test')]
    return not any(a & b for a, b in itertools.combinations(groups, 2)) and len(task['pool']) == len(task['teacher_answers'])


def allowed(task, context):
    return sorted({r['label'] for r in task['completion_oracle'] if all(r['context'][f] == v for f, v in context.items())})


def queries(task):
    complete = [{'context': r['context'], 'allowed': [r['label']]} for r in task['test']]
    partial = []
    seen = set()
    for row in task['test']:
        for f in sorted(row['context']):
            c = {k: v for k, v in row['context'].items() if k != f}
            k = canonical(c)
            if k not in seen:
                seen.add(k)
                partial.append({'context': c, 'allowed': allowed(task, c)})
    partial.append({'context': {}, 'allowed': allowed(task, {})})
    return [('complete', complete), ('semantic_missing', partial)]


if __name__ == '__main__':
    for split in ('development', 'evaluation'):
        with (ROOT / 'data' / (split + '.json')).open('x', encoding='utf-8') as f:
            f.write(json.dumps(tasks(split), ensure_ascii=False, indent=2) + '\n')
