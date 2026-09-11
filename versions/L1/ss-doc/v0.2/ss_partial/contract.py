"""Designed observation, target-address and external-update contracts."""
import itertools
from plm_l1_v09.component.algebra import require
from plm_l1_v09.component.lexicon import ROLES
from ss_document.contract import IDS, normalize as normalize_meaning, edge

STATES = ('known', 'ambiguous', 'unobserved', 'unreadable', 'conflict')
TIME_VALUES = ('unspecified', 'before', 'after')


def cell(state, candidates):
    return {'state': state, 'candidates': list(candidates)}


def event_address(identity, role):
    return identity + '/' + role


def time_address(pair):
    return 'time/' + ','.join(pair)


def inventory(n, candidates):
    result = {event_address(i, r): tuple(candidates[r]) for i in IDS[:n] for r in ROLES}
    result.update({time_address(p): TIME_VALUES for p in itertools.combinations(IDS[:n], 2)})
    return result


def normalize_cell(value, choices):
    require(type(value) is dict and set(value) == {'state', 'candidates'}, 'cell_fields')
    state, values = value['state'], value['candidates']
    require(type(state) is str and state in STATES, 'observation_state')
    require(type(values) is list and all(type(v) is str and v in choices for v in values), 'candidate_inventory')
    require(len(set(values)) == len(values), 'duplicate_candidates')
    n = len(values)
    require((state == 'known' and n == 1) or (state == 'ambiguous' and n == 2) or
            (state in ('unobserved', 'unreadable') and n == 0) or (state == 'conflict' and n >= 2), 'state_cardinality')
    return cell(state, [v for v in choices if v in values])


def normalize(observation, candidates):
    require(type(observation) is dict and set(observation) == {'count', 'presentation', 'cells'}, 'observation_fields')
    n = observation['count']
    require(type(n) is int and n in (2, 3), 'two_or_three_events')
    order = observation['presentation']
    require(type(order) is list and len(order) == n and all(type(i) is str for i in order) and set(order) == set(IDS[:n]), 'presentation')
    inv = inventory(n, candidates)
    require(type(observation['cells']) is dict and set(observation['cells']) == set(inv), 'complete_cell_inventory')
    cells = {k: normalize_cell(observation['cells'][k], choices) for k, choices in inv.items()}
    adjacent = {time_address(sorted(p)) for p in zip(order, order[1:])}
    for key in inv:
        if key.startswith('time/') and key not in adjacent:
            require(cells[key] == cell('known', ['unspecified']), 'nonadjacent_time_must_remain_unspecified')
    return {'count': n, 'presentation': list(order), 'cells': cells}


def from_meaning(meaning, candidates):
    m = normalize_meaning(meaning, candidates)
    cells = {event_address(e['id'], r): cell('known', [e[r]]) for e in m['events'] for r in ROLES}
    for relation in m['relations']:
        value = 'unspecified' if relation['kind'] == 'unknown' else 'before' if relation['source'] == relation['pair'][0] else 'after'
        cells[time_address(relation['pair'])] = cell('known', [value])
    return normalize({'count': len(m['events']), 'presentation': m['presentation'], 'cells': cells}, candidates)


def to_meaning(observation, candidates):
    o = normalize(observation, candidates)
    require(all(c['state'] == 'known' for c in o['cells'].values()), 'unresolved_meaning')
    events = [dict(id=i, **{r: o['cells'][event_address(i, r)]['candidates'][0] for r in ROLES}) for i in IDS[:o['count']]]
    relations = []
    for a, b in itertools.combinations(IDS[:o['count']], 2):
        value = o['cells'][time_address((a, b))]['candidates'][0]
        relations.append(edge(a, b) if value == 'unspecified' else edge(a, b, a, b) if value == 'before' else edge(a, b, b, a))
    return normalize_meaning({'events': events, 'presentation': o['presentation'], 'relations': relations}, candidates)


def pending(observation):
    return [{'target': k, **c} for k, c in observation['cells'].items() if c['state'] != 'known']
