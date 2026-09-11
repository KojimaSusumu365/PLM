"""Post-run independent bookkeeping of intended edits and rendered transition outputs."""
import copy
import itertools
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, verify
from evaluation.oracle import localize, scored


def meaning(observation):
    ids = [f'event:{i}' for i in range(observation['count'])]
    roles = ('subject', 'object', 'predicate', 'polarity', 'modality')
    events = [dict(id=i, **{r: observation['cells'][i+'/'+r]['candidates'][0] for r in roles}) for i in ids]
    relations = []
    for a, b in itertools.combinations(ids, 2):
        value = observation['cells']['time/'+a+','+b]['candidates'][0]
        relations.append({'pair': [a, b], 'kind': 'unknown' if value == 'unspecified' else 'before',
                          'source': None if value == 'unspecified' else a if value == 'before' else b,
                          'target': None if value == 'unspecified' else b if value == 'before' else a})
    return {'events': events, 'relations': relations, 'presentation': observation['presentation']}


def main():
    verify(); ev = read(ROOT / 'results/EVALUATION.json'); cases = {c['id']: c for c in read(ROOT / 'results/CASES.json')}
    counts = {}; checked = 0
    for probe in ev['probes']:
        for group in probe.get('transitions', []):
            case = cases[group['case_id']]
            for row in group['rows']:
                label = row['label']; assert row['input_unchanged']
                if label in ('explicit_resolve', 'correct_supply', 'explicit_revise', 'in_candidate_wrong_teacher'):
                    expected = copy.deepcopy(case['expected_observation'])
                    if label in ('explicit_revise', 'in_candidate_wrong_teacher'):
                        expected['cells'][case['target']] = {'state': 'known', 'candidates': [case['alternate_value']]}
                    assert row['observation'] == expected
                    m = meaning(expected)
                    score = scored(localize(m, m['presentation'], ['subject'] * expected['count']), row['generation']['text'])
                    assert score['semantic_equal'] and score['goals_equal']
                    counts[label] = counts.get(label, 0) + 1; checked += 1
                elif label in ('known_disagreement', 'supply_does_not_resolve_conflict', 'outside_candidate_conflict'):
                    assert row['observation']['cells'][case['target']]['state'] == 'conflict'
                    assert row['generation']['status'] == 'needs_information' and 'text' not in row['generation']
                    assert all(row['observation']['cells'][k] == c for k, c in case['expected_observation']['cells'].items() if k != case['target'])
                elif label in ('stale_replay', 'unknown_value'):
                    assert row['update']['status'] == 'rejected' and 'observation' not in row
    write(ROOT / 'verification/TRANSITION_AUDIT.json', {'passed': True, 'independent_intended_update_and_generation_checks': checked,
          'counts': counts, 'note': 'Wrong-teacher outputs correctly follow the supplied value but are wrong against original world labels; no source/settings changes.'})
    print({'passed': True, 'checked': checked, 'counts': counts})


if __name__ == '__main__': main()
