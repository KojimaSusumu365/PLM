import numpy as np
from ss_multicode.model import decide, policy
from ss_active.selection import context_id
from .cases import truth_map


def raw(scores):
    return {'readers': np.asarray(scores), 'checker': np.empty((len(scores), 0))}


def probe_context(case):
    rows = [r for g in 'ABCD' for r in case['groups'][g]]
    rows += [{'id': context_id(c), 'context': c} for c in case['unknown']]
    return rows


def counts(scores, known, truth):
    ds = decide(raw(scores), policy()); known = np.asarray(known); truth = np.asarray(truth)
    out = {'requests': len(scores), 'known_requests': int(known.sum()), 'unseen_requests': int((~known).sum())}
    for field in ('tentative', 'accepted'):
        v = ds[field]
        out[field+'_correct'] = int((known & (v == truth)).sum())
        out[field+'_wrong'] = int((known & (v >= 0) & (v != truth)).sum())
        out[field+'_abstained'] = int((known & (v < 0)).sum())
    out['unseen_false_accept'] = int(((~known) & (ds['accepted'] >= 0)).sum())
    out['unseen_rejected'] = out['unseen_requests'] - out['unseen_false_accept']
    return out


def summarize(scores, case, scenario, acquired, after_challenge, baseline_scores, pre_scores, corrected_ids):
    rows = probe_context(case); ids = [r['id'] for r in rows]; truthmap = truth_map(case, scenario)
    truth = np.array([int(truthmap.get(k, '-1')) for k in ids]); g = case['size']
    base_known = np.arange(len(rows)) < 3*g
    known = np.arange(len(rows)) < (4*g if after_challenge else 3*g)
    pool = {r['id'] for r in case['pool']}; selected = set(acquired)
    changed = set(case['changed_ids']) if scenario == 'changed_pool16' else set()
    groups = {name: np.arange(i*g, (i+1)*g) for i, name in enumerate('ABCD')}
    groups.update({'old_all': np.arange(2*g), 'learned_ABC': np.arange(3*g), 'never_taught': np.arange(4*g, 4*g+128),
                   'old_stable': np.array([i for i in range(2*g) if ids[i] not in changed], dtype=int),
                   'pool': np.array([i for i,k in enumerate(ids) if k in pool], dtype=int),
                   'pool_selected': np.array([i for i,k in enumerate(ids) if k in selected], dtype=int),
                   'pool_unselected': np.array([i for i,k in enumerate(ids) if k in pool-selected], dtype=int),
                   'protected_old': np.array([i for i in range(2*g) if ids[i] not in pool], dtype=int),
                   'changed_pool': np.array([i for i,k in enumerate(ids) if k in changed], dtype=int)})
    current = decide(raw(scores), policy()); base = decide(raw(baseline_scores), policy()); pre = decide(raw(pre_scores), policy())
    output = {}
    for name, ix in groups.items():
        m = counts(scores[ix], known[ix], truth[ix]); transitions = {}
        for field in ('tentative', 'accepted'):
            domain = base_known[ix]
            bc = (base[field][ix] == truth[ix]) & domain
            cc = (current[field][ix] == truth[ix]) & domain
            pc = (pre[field][ix] == truth[ix]) & domain
            transitions[field+'_baseline_correct'] = int(bc.sum())
            transitions[field+'_newly_correct'] = int((cc & ~bc).sum())
            transitions[field+'_lost_baseline_correct'] = int((bc & ~cc).sum())
            transitions[field+'_recovered_before_challenge'] = int((pc & ~bc).sum())
            transitions[field+'_recovery_lost_after_challenge'] = int((pc & ~bc & ~cc).sum()) if after_challenge else 0
        m['transitions'] = transitions; output[name] = m
    ix = np.array([i for i,k in enumerate(ids) if k in set(corrected_ids)], dtype=int)
    values = current['tentative'][ix]
    recurrence = {'previously_corrected_selected_tentative_errors': len(ix),
                  'now_correct': int((values == truth[ix]).sum()),
                  'again_wrong': int(((values >= 0) & (values != truth[ix])).sum()),
                  'now_abstained': int((values < 0).sum())}
    return {'groups': output, 'correction_recurrence': recurrence}
