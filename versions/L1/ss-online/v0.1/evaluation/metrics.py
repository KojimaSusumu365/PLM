from collections import Counter
from ss_online.model import decisions


def probe_metrics(scores,rows,known_ids,truth):
    ps=decisions(scores,list('0123'));m=Counter(requests=len(rows))
    for r,p in zip(rows,ps):
        if r['id'] in known_ids:
            m['known_requests']+=1
            for field in ('tentative','accepted'):
                m[field+'_correct' if p[field]==truth[r['id']] else field+'_abstained' if p[field] is None else field+'_wrong']+=1
        else:
            m['unseen_requests']+=1
            m['unseen_false_accept' if p['accepted'] is not None else 'unseen_rejected']+=1
            m['unseen_tentative_guesses']+=int(p['tentative'] is not None)
    for key in ('known_requests','tentative_correct','tentative_wrong','tentative_abstained','accepted_correct','accepted_wrong','accepted_abstained','unseen_requests','unseen_false_accept','unseen_rejected','unseen_tentative_guesses'):m.setdefault(key,0)
    return dict(m)


def trace_metrics(rows):
    result=Counter(presentations=len(rows))
    for r in rows:
        for stage in ('before','after'):
            for field in ('tentative','accepted'):
                val=r[stage][field]
                result[f'{stage}_{field}_'+('correct' if val==r['truth'] else 'abstained' if val is None else 'wrong')]+=1
        result['wrong_teacher_answers']+=int(r['teacher_label']!=r['truth'])
        result['repeated_key_exposures']+=int(r['seen_before'])
        result['previous_tentative_error_exposures']+=int(r['previous_tentative_error'])
        result['recurring_tentative_errors']+=int(r['previous_tentative_error'] and r['before']['tentative'] is not None and r['before']['tentative']!=r['truth'])
        result['corrected_previous_tentative_errors']+=int(r['previous_tentative_error'] and r['before']['tentative']==r['truth'])
        result['numerical_or_exact_updates']+=r['updates']
        result['replay_updates']+=r['replay_updates']
    return dict(result)
