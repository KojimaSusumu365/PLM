from collections import Counter
import math
import numpy as np
from ss_multicode.model import decide, policy, SPECS


def fixed_policies(architecture):
    k, _, _, cd = SPECS[architecture]
    ps = {'mean': policy()}
    if k > 1:
        ps['quorum'] = policy(quorum=math.ceil(.75 * k))
        ps['unanimous'] = policy(quorum=k)
    if cd:
        ps['pair_check'] = policy(check_threshold=.5)
        ps['quorum_pair_check'] = policy(quorum=math.ceil(.75 * k), check_threshold=.5)
    return ps


def grid(architecture):
    k, _, _, cd = SPECS[architecture]
    return [policy(round(.25 + .05 * i, 2), q, ch) for i in range(21)
            for q in (range(k + 1) if k > 1 else [0])
            for ch in ([None, .25, .5, .75, 1.] if cd else [None])] + [policy(reject_all=True)]


def metrics(raw, p, known, truth):
    known = np.asarray(known, dtype=bool); truth = np.asarray(truth, dtype=int)
    ds = decide(raw, p); out = {'requests': len(known), 'known_requests': int(known.sum()), 'unseen_requests': int((~known).sum())}
    for field in ('tentative', 'accepted'):
        vals = ds[field]
        out[field + '_correct'] = int((known & (vals == truth)).sum())
        out[field + '_wrong'] = int((known & (vals >= 0) & (vals != truth)).sum())
        out[field + '_abstained'] = int((known & (vals < 0)).sum())
    out['unseen_false_accept'] = int(((~known) & (ds['accepted'] >= 0)).sum())
    out['unseen_rejected'] = int(((~known) & (ds['accepted'] < 0)).sum())
    return out


def subset(raw, indexes):
    return {key: value[indexes] for key, value in raw.items()}


def case_probes(case, known_ids, drift=False):
    rows = [r for g in ('A', 'B', 'C') for r in case['groups'][g]]
    rows += [{'id': f'unknown-{i}', 'context': c, 'label': '-1'} for i, c in enumerate(case['unknown'])]
    truth = np.array([((int(r['label']) + 1) % 4 if drift and r['id'] in case['changed_A_ids'] else int(r['label'])) for r in rows])
    known = np.array([r['id'] in known_ids for r in rows])
    return rows, known, truth


def snapshot_summary(raw, policies, case, known_ids, phase, epoch, anchors):
    rows, known, truth = case_probes(case, known_ids, phase == 'drift')
    indices = {'A': np.arange(64), 'B': np.arange(64, 128), 'C': np.arange(128, 192), 'never_taught': np.arange(192, 320)}
    if phase == 'drift':
        indices['changed_A'] = np.array([i for i, r in enumerate(rows[:64]) if r['id'] in case['changed_A_ids']])
        indices['unchanged_A'] = np.array([i for i, r in enumerate(rows[:64]) if r['id'] not in case['changed_A_ids']])
    out = {}
    stable = set(indices.get('unchanged_A', np.arange(64)).tolist())
    mean_decisions = decide(raw, policy())
    for name, p in policies.items():
        ds = decide(raw, p); correct = {i for i in range(64) if known[i] and ds['accepted'][i] == truth[i]}
        if phase == 'A' and epoch == 4: anchors[name] = correct
        anchor = anchors.get(name)
        out[name] = {'groups': {g: metrics(subset(raw, ix), p, known[ix], truth[ix]) for g, ix in indices.items()},
                     'forgetting': {'anchor_defined': anchor is not None, 'anchor_correct': len((anchor or set()) & stable),
                                    'lost_anchor_correct': len(((anchor or set()) & stable) - correct)},
                     'versus_mean': {
                         'known_correct_discarded': int((known & (mean_decisions['accepted'] == truth) & (ds['accepted'] < 0)).sum()),
                         'known_wrong_discarded': int((known & (mean_decisions['accepted'] >= 0) & (mean_decisions['accepted'] != truth) & (ds['accepted'] < 0)).sum()),
                         'unseen_accept_discarded': int(((~known) & (mean_decisions['accepted'] >= 0) & (ds['accepted'] < 0)).sum())}}
    return out


def trace_summary(before, after, events, policies):
    truth = np.array([int(e['truth']) for e in events]); out = {}
    for name, p in policies.items():
        bd = decide(before, p); ad = decide(after, p); previous = {}; blocks = {}
        for i, e in enumerate(events):
            key = (e['phase'], e['epoch']); m = blocks.setdefault(key, Counter(presentations=0)); m['presentations'] += 1
            for stage, ds in (('before', bd), ('after', ad)):
                for field in ('tentative', 'accepted'):
                    v = ds[field][i]
                    m[f'{stage}_{field}_' + ('correct' if v == truth[i] else 'abstained' if v < 0 else 'wrong')] += 1
            prev = previous.get((e['id'], e['truth']), False)
            m['previous_tentative_error_exposures'] += int(prev)
            m['recurring_tentative_errors'] += int(prev and bd['tentative'][i] >= 0 and bd['tentative'][i] != truth[i])
            m['corrected_previous_tentative_errors'] += int(prev and bd['tentative'][i] == truth[i])
            m['wrong_teacher_answers'] += int(e['teacher_label'] != e['truth'])
            previous[e['id'], e['truth']] = bd['tentative'][i] >= 0 and bd['tentative'][i] != truth[i]
        out[name] = [{'phase': k[0], 'epoch': k[1], 'metrics': dict(m)} for k, m in blocks.items()]
    return out


def calibration_rows(architecture, records):
    results = []
    for i, p in enumerate(grid(architecture)):
        totals = Counter()
        for record in records:
            # Already restricted to seen keys and the dedicated never-taught validation set.
            totals.update(metrics(record['raw'], p, record['known'], record['truth']))
        accepted = totals['accepted_correct'] + totals['accepted_wrong']
        eligible = (totals['unseen_false_accept'] * 100 <= totals['unseen_requests'] and
                    (accepted == 0 or totals['accepted_wrong'] * 100 <= accepted))
        results.append({'grid_index': i, 'policy': p, 'metrics': dict(totals), 'feasible': eligible})
    feasible = [r for r in results if r['feasible']]
    best = min(feasible, key=lambda r: (-r['metrics']['accepted_correct'], r['metrics']['unseen_false_accept'],
                                       r['metrics']['accepted_wrong'], r['grid_index']))
    return results, best
