import json
import random
from pathlib import Path
from .oracle import render

ROOT = Path(__file__).resolve().parents[1]

def build():
    lex = json.loads((ROOT/'data/lexicon.json').read_text(encoding='utf-8'))['slot_candidates']
    seen = set()
    splits = {}
    for split, count in (('development', 4), ('evaluation', 24)):
        rng = random.Random('ss-wave03-cases/'+split)
        rows = []
        for i in range(count):
            while True:
                events = []
                for j in range(2):
                    a, b = rng.sample(lex['subject'], 2)
                    events.append({'id': f'event:{j}', 'subject': a, 'object': b,
                                   'predicate': rng.choice(lex['predicate']),
                                   'polarity': lex['polarity'][(i+j)%2],
                                   'modality': lex['modality'][(i//2+j)%2]})
                relation = i%3
                m = {'events': events, 'presentation': ['event:0', 'event:1'], 'relations': [
                    {'pair': ['event:0', 'event:1'], 'kind': 'unknown' if relation == 0 else 'before',
                     'source': None if relation == 0 else 'event:0' if relation == 1 else 'event:1',
                     'target': None if relation == 0 else 'event:1' if relation == 1 else 'event:0'}]}
                signature = json.dumps(m, sort_keys=True)
                if signature not in seen:
                    seen.add(signature)
                    break
            rows.append({'id': split+'/'+str(i), 'meaning': m,
                         'text': render(m, ['subject' if (i+j)%2 == 0 else 'object' for j in range(2)])})
        splits[split] = rows
    return {'schema': 'ss-wave03-corpus', 'splits': splits,
            'scope': 'known_vocabulary_two_events_no_raw_corpus_grammar_learning',
            'split_disjoint': True, 'prior_all_history_exclusion_claimed': False,
            'controller_training_contains_entity_or_predicate_values': False}
