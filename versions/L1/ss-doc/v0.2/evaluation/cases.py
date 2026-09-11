import copy
import itertools
import random
from plm_l1_v09.component.algebra import canonical
from ss_partial.contract import from_meaning, cell, inventory, normalize
from .integrity import ROOT, read
from .oracle import render


def scene_key(events):
    return canonical(sorted([{k: v for k, v in event.items() if k != 'id'} for event in events], key=canonical))


def scenes(split):
    lex = read(ROOT / 'data/lexicon.json')['slot_candidates']
    forbidden = {scene_key(p['meaning']['events']) for p in read(ROOT / 'data/temporal_train.json')}
    forbidden |= {scene_key(p['meaning']['events']) for p in read(ROOT / 'data/doc_v01_regression.json')}
    if split == 'evaluation':
        forbidden |= {scene_key(p['meaning']['events']) for p in scenes('development')}
    rng = random.Random('ss-partial-v02/' + split)
    count = 2 if split == 'development' else 4
    result = []
    for n in (2, 3):
        for index in range(count):
            while True:
                events = []
                for i in range(n):
                    a, b = rng.sample(lex['subject'], 2)
                    events.append({'id': f'event:{i}', 'subject': a, 'object': b,
                                   **{r: rng.choice(lex[r]) for r in ('predicate', 'polarity', 'modality')}})
                key = scene_key(events)
                if key not in forbidden:
                    forbidden.add(key)
                    break
            relations = []
            for i, j in itertools.combinations(range(n), 2):
                k = (index + i) % 3 if j == i + 1 else 0
                a, b = f'event:{i}', f'event:{j}'
                relations.append({'pair': [a, b], 'kind': 'unknown' if k == 0 else 'before',
                                  'source': None if k == 0 else a if k == 1 else b,
                                  'target': None if k == 0 else b if k == 1 else a})
            m = {'events': events, 'relations': relations, 'presentation': [f'event:{i}' for i in range(n)]}
            result.append({'id': f'{split}/{n}/{index}', 'meaning': m,
                           'text': render(m, [('subject', 'object')[(index+i) % 2] for i in range(n)])})
    return result


def alternate(known, target, choices):
    original = known['cells'][target]['candidates'][0]
    excluded = {original}
    if target.endswith('/subject'):
        excluded.add(known['cells'][target.replace('/subject', '/object')]['candidates'][0])
    if target.endswith('/object'):
        excluded.add(known['cells'][target.replace('/object', '/subject')]['candidates'][0])
    return next(v for v in choices if v not in excluded)


def cases(split):
    lex = read(ROOT / 'data/lexicon.json')['slot_candidates']
    result = []
    for scene in scenes(split):
        known = from_meaning(scene['meaning'], lex)
        for target, choices in inventory(known['count'], lex).items():
            if target == 'time/event:0,event:2':
                continue
            truth = known['cells'][target]['candidates'][0]
            other = alternate(known, target, choices)
            for state in ('ambiguous', 'unobserved', 'unreadable'):
                o = copy.deepcopy(known)
                o['cells'][target] = cell(state, [truth, other] if state == 'ambiguous' else [])
                result.append({'id': scene['id'] + '/' + target + '/' + state, 'scene_id': scene['id'],
                               'observation': normalize(o, lex), 'expected_observation': known,
                               'target': target, 'teacher_value': truth, 'alternate_value': other,
                               'expected_meaning': scene['meaning']})
    return result
