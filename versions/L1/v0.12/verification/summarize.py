import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(result):
    sums = {}
    families = {}
    for run in result['runs']:
        group = 'small' if run['task_id'].endswith('/small') else 'ambiguity' if run['family'] == 'ambiguity' else ('hidden_' + run['task_id'].rsplit('/', 1)[-1]) if run['family'] == 'unseen_interaction' else 'structured' if run['family'] in ('roles', 'polarity_modality') else 'standard'
        for stage in run['stages']:
            for policy, metrics in stage['metrics'].items():
                key = (run['category'], group, run['method'], run['dimension'], run['after'], stage['kind'], policy)
                for target, extra in ((sums, ()), (families, (run['family'],))):
                    counter = target.setdefault(key + extra, Counter())
                    counter['runs'] += 1
                    counter.update({k: v for k, v in metrics.items() if type(v) is int})
    fields = ('category', 'group', 'method', 'dimension', 'after', 'kind', 'policy')
    def materialize(mapping, extra=()):
        rows = []
        for key, value in mapping.items():
            row = dict(zip(fields + extra, key), **value)
            row['coverage'] = row['accepted'] / row['requests'] if row['requests'] else None
            row['selective_risk'] = row['wrong'] / row['accepted'] if row['accepted'] else None
            rows.append(row)
        return rows
    return {'models': len(result['runs']), 'checks': len(result['checks']), 'checks_by_kind': dict(Counter(c['kind'] for c in result['checks'])),
            'all_checks_passed': result['all_checks_passed'], 'aggregates': materialize(sums), 'families': materialize(families, ('family',)),
            'prior_baseline_models': len(result['v011_comparison']), 'prior_baseline_probes': sum(r['probes'] for r in result['v011_comparison']),
            'witness_stress': [{k: v for k, v in r.items() if k != 'predictions'} for r in result['witness_stress']]}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--result', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    r = summarize(json.loads(Path(a.result).read_text(encoding='utf-8')))
    with Path(a.out).open('x', encoding='utf-8') as f:
        f.write(json.dumps(r, ensure_ascii=False, indent=2) + '\n')
    for row in r['aggregates']:
        if row['dimension'] == 2048 and row['kind'] == 'semantic_missing' and row['group'] in ('standard', 'hidden_hidden'):
            print(row['category'], row['group'], row['method'], row['policy'], row['correct'], row['wrong'], row['abstained'])
