import copy
import itertools
import json
import random
from .tasks import ROOT, FAMILIES, make_task, allowed, semantic_queries
from plm_l1_v011.algebra import canonical


def paired_worlds(split):
    rng = random.Random('v012/hidden/' + split)
    groups = []
    for a, b, c in itertools.product((0, 1), repeat=3):
        noise = list(itertools.product((0, 1), repeat=3))
        rng.shuffle(noise)
        groups.append([{'context': dict(zip(('a', 'b', 'c', 'n0', 'n1', 'n2'), map(str, (a, b, c) + n))),
                        'label': str(a)} for n in noise])
    shared = {'family': 'unseen_interaction', 'train': [r for g in groups[:7] for r in g[:3]],
              'selection': [r for g in groups[:7] for r in g[3:5]],
              'calibration': [g[5] for g in groups[:7]],
              'test': [r for g in groups[:7] for r in g[6:]] + groups[7],
              'completion_oracle': [r for g in groups for r in g]}
    worlds = []
    for world in ('simple', 'hidden'):
        task = copy.deepcopy(shared)
        task['id'] = f'v012-{split}/unseen_interaction/{world}'
        if world == 'hidden':
            for name in ('test', 'completion_oracle'):
                for row in task[name]:
                    if all(row['context'][f] == '1' for f in ('a', 'b', 'c')):
                        row['label'] = '0'
        task['scope'] = 'Paired worlds with indistinguishable training evidence; evaluator-only hidden interaction is never sent to the learner.'
        worlds.append(task)
    return worlds


def new_tasks(split):
    return [make_task('v012-' + split, family, rep) for family in FAMILIES
            for rep in range(2 if family not in ('roles', 'polarity_modality') else 1)] + paired_worlds(split)


def query_stages(task, two_missing=False):
    result = [('complete', [{'context': r['context'], 'allowed': [r['label']]} for r in task['test']]),
              ('semantic_missing', semantic_queries(task))]
    if two_missing:
        seen = set()
        queries = []
        for row in task['test']:
            for erased in itertools.combinations(sorted(row['context']), 2):
                c = {f: v for f, v in row['context'].items() if f not in erased}
                key = canonical(c)
                if key not in seen:
                    seen.add(key)
                    queries.append({'context': c, 'allowed': allowed(task, c)})
        result.append(('semantic_two_missing', queries))
    result.append(('unknown_values', [{'context': {f: 'not-registered' for f in task['train'][0]['context']}, 'allowed': []}]))
    return result


if __name__ == '__main__':
    for split in ('development', 'evaluation'):
        with (ROOT / 'data' / (split + '.json')).open('x', encoding='utf-8') as f:
            f.write(json.dumps(new_tasks(split), ensure_ascii=False, indent=2) + '\n')
