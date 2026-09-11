import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def summarize(result):
    sums = {}
    families = {}
    costs = {}
    teacher_pairs = []
    for run in result['runs']:
        family = run['family']
        group = family if family.startswith('paired_') or family == 'outside_order4' else 'structured' if family in ('roles', 'polarity_modality') else 'standard'
        for snap in run['snapshots']:
            for stage in snap['stages']:
                k = (group, run['method'], run['backend'], run['dimension'], snap['budget'], stage['kind'])
                for target, extra in ((sums, ()), (families, (family,))):
                    c = target.setdefault(k + extra, Counter())
                    c['trajectories'] += 1
                    c['labels_used_total'] += snap['labels_used']
                    c.update({name: value for name, value in stage['metrics'].items() if type(value) is int})
                    c.update({'reason/' + p['reason']: 1 for p in []})
                    for p in stage['predictions']:
                        c['reason/' + p['reason']] += 1
                ck = (group, run['method'], run['backend'], run['dimension'], snap['budget'])
                if stage['kind'] == 'complete':
                    costs.setdefault(ck, []).append({'labels_used': snap['labels_used'], **snap['storage']})
    fields = ('group', 'method', 'backend', 'dimension', 'budget', 'kind')
    def rows(mapping, extra=()):
        output = []
        for k, value in mapping.items():
            row = dict(zip(fields + extra, k), **value)
            row['coverage'] = row['accepted'] / row['requests'] if row['requests'] else None
            row['selective_risk'] = row['wrong'] / row['accepted'] if row['accepted'] else None
            row['mean_labels_used'] = row['labels_used_total'] / row['trajectories']
            output.append(row)
        return output
    for active in [r for r in result['runs'] if r['method'] == 'all/active']:
        random = next(r for r in result['runs'] if r['method'] == 'all/random' and all(r[k] == active[k] for k in ('task_id', 'backend', 'dimension', 'code_seed', 'acquisition_seed')))
        for a, b in zip(active['snapshots'], random['snapshots']):
            for x, y in zip(a['stages'], b['stages']):
                teacher_pairs.append({'task_id': active['task_id'], 'family': active['family'], 'backend': active['backend'], 'dimension': active['dimension'],
                                      'code_seed': active['code_seed'], 'acquisition_seed': active['acquisition_seed'], 'budget': a['budget'], 'kind': x['kind'],
                                      'active_labels': a['labels_used'], 'random_labels': b['labels_used'], 'same_actual_teacher_count': a['labels_used'] == b['labels_used'],
                                      'correct_difference': x['metrics']['correct'] - y['metrics']['correct'], 'wrong_difference': x['metrics']['wrong'] - y['metrics']['wrong']})
    cost_rows = []
    for k, data in costs.items():
        row = dict(zip(fields[:-1], k))
        for name in ('candidate_count', 'complex_weight_bytes', 'metadata_utf8_bytes', 'integer_entries', 'warm_atom_bytes', 'labels_used'):
            row[name] = {'min': min(x[name] for x in data), 'median': statistics.median(x[name] for x in data), 'max': max(x[name] for x in data)}
        cost_rows.append(row)
    return {'sessions': len(result['runs']), 'checkpoints': sum(len(r['snapshots']) for r in result['runs']),
            'checks': len(result['checks']), 'checks_by_kind': dict(Counter(c['kind'] for c in result['checks'])),
            'all_checks_passed': result['all_checks_passed'], 'aggregates': rows(sums), 'families': rows(families, ('family',)),
            'costs': cost_rows, 'matched_teacher_pairs': teacher_pairs,
            'full_pool_equality': result['full_pool_checks'], 'paired_worlds': result['paired_worlds']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--result', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    result = summarize(json.loads(Path(a.result).read_text(encoding='utf-8')))
    with Path(a.out).open('x', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    for row in result['aggregates']:
        if row['dimension'] == 2048 and row['kind'] == 'complete' and row['group'] in ('standard', 'paired_hidden'):
            print(row['group'], row['method'], row['budget'], row['correct'], row['wrong'], row['abstained'], 'teachers', row['mean_labels_used'])
