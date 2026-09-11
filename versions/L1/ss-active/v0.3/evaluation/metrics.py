"""All teacher labels and correction/cohort flags remain evaluator-only."""
import numpy as np
from ss_trace.runtime import choice, diagnostics, binary_stats


def counts(pred, labels, indices):
    ix = np.array(indices, int); labels = np.array(labels, int)
    return {'n': len(ix), 'accepted_correct': int(((pred['accepted'][ix] == labels[ix]) & (labels[ix]>=0)).sum()),
            'accepted_wrong': int(((pred['accepted'][ix] >= 0) & (pred['accepted'][ix] != labels[ix])).sum()),
            'abstain': int((pred['accepted'][ix] < 0).sum()),
            'tentative_correct': int(((pred['tentative'][ix] == labels[ix]) & (labels[ix]>=0)).sum())}


def measure(main, aux, probe_rows, ledger, step, last, world_truth, corrected_first, taught_correct, size, pool_ids):
    ids = [r['id'] for r in probe_rows]; index = {k:i for i,k in enumerate(ids)}
    ds = diagnostics(main, aux, ids, ledger, step); p = choice(main)
    labels = [int(world_truth[k]) if k in world_truth else -1 for k in ids]
    old = list(range(2*size)); unknown = list(range(5*size, 5*size+128))
    protected = [i for i in old if ids[i] not in pool_ids]
    out = {'old': counts(p, labels, old), 'protected': counts(p, labels, protected),
           'unknown_main': counts(p, labels, unknown), 'cohorts': {}}
    for name, keys in [('all_acquired',set(last)), ('immediately_correct',set(taught_correct)), ('first_corrected',set(corrected_first))]:
        keys = sorted(keys); ix = np.array([index[k] for k in keys], int)
        last_labels = np.array([int(last[k]) for k in keys], int)
        truth_labels = np.array([int(world_truth[k]) for k in keys], int)
        # A tie is counted as a failure to retain a definite taught answer, not an accepted wrong answer.
        forgotten = ds['main_tentative'][ix] != last_labels
        world_wrong = ds['main_tentative'][ix] != truth_labels
        row = {'n': len(keys), 'teacher_aligned_failures': int(forgotten.sum()),
               'world_failures': int(world_wrong.sum()), 'stale_teachers': int((last_labels!=truth_labels).sum()),
               'detectors': {}}
        for detector in ('gap_drop','ss_disagreement','ss_weak_support'):
            alarm = ds[detector][ix]
            rank = sorted([j for j in range(len(ix)) if alarm[j]],
                          key=lambda j: ((ds['main_margin'][ix[j]] if detector=='gap_drop' else -ds['priority'][ix[j]]),keys[j]))[:4]
            row['detectors'][detector] = {
                'last_teacher': binary_stats(forgotten, alarm), 'current_world': binary_stats(world_wrong, alarm),
                'shadow_top4': {'hypothetical_teachers':len(rank), 'teacher_error_hits':int(forgotten[rank].sum()),
                                'world_error_hits':int(world_wrong[rank].sum())}}
        if aux.shape[1]:
            ac = ds['aux_confident'][ix]; al = ds['aux_accepted'][ix]
            row['trace'] = {'confident':int(ac.sum()), 'confident_correct_last_teacher':int((ac & (al==last_labels)).sum()),
                            'confident_wrong_last_teacher':int((ac & (al!=last_labels)).sum()),
                            'confident_wrong_world':int((ac & (al!=truth_labels)).sum()),
                            'both_agree_obsolete':int((ac & (al==ds['main_tentative'][ix]) & (al==last_labels) & (last_labels!=truth_labels)).sum())}
        out['cohorts'][name] = row
    out['unknown_trace'] = {'n':128, 'accepted':int((ds['aux_accepted'][unknown]>=0).sum()),
                            'confident':int(ds['aux_confident'][unknown].sum()),
                            'eligible_alarms':int(ds['ss_disagreement'][unknown].sum())}
    return out
