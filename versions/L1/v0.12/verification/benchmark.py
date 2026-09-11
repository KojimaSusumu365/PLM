"""Posthoc single-process cost diagnostic; no model tuning."""
import json
import platform
import statistics
import sys
import time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plm_l1_v012.core import POLICIES
from plm_l1_v012.training import train_model
from evaluation.tasks import semantic_queries
from evaluate import write


def main():
    tasks = json.loads((ROOT / 'data/v011-regression.json').read_text(encoding='utf-8'))
    tasks = [t for t in tasks if t['family'] in ('unary', 'and2', 'parity3') and t['id'].endswith('/0')]
    records = []
    for task in tasks:
        for backend in ('ss', 'exact'):
            for trial in range(3):
                m, _, fit = train_model(task['train'], task['selection'], task['calibration'], backend=backend, dimension=2048, seed='evaluation-0')
                for kind, contexts in (('complete', [r['context'] for r in task['test']]), ('semantic_missing', [r['context'] for r in semantic_queries(task)])):
                    for policy in POLICIES:
                        for c in contexts:
                            m.predict(c, policy=policy)
                        started = time.perf_counter()
                        branch_counts = []
                        for c in contexts:
                            branch_counts.append(m.predict(c, policy=policy)['completion_count'])
                        elapsed = time.perf_counter() - started
                        records.append({'task_id': task['id'], 'backend': backend, 'trial': trial, 'kind': kind, 'policy': policy,
                                        'query_seconds_per_request': elapsed / len(contexts), 'queries': len(contexts),
                                        'maximum_completions': max(branch_counts), 'mean_completions': statistics.mean(branch_counts),
                                        'base_fit_seconds': fit['fit_seconds'], 'attach_seconds': fit['attach_seconds'], 'storage': m.storage()})
    result = {'scope': 'Single process after both final evaluations. Three prelisted structured tasks, D2048/first seed, 3 repeats, warm queries. Not pure kernel time, whole language, RSS, power or general latency.',
              'environment': {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()}, 'rows': records, 'medians': []}
    for backend in ('ss', 'exact'):
        for kind in ('complete', 'semantic_missing'):
            for policy in POLICIES:
                rs = [r for r in records if r['backend'] == backend and r['kind'] == kind and r['policy'] == policy]
                value = statistics.median(statistics.median(r['query_seconds_per_request'] for r in rs if r['task_id'] == t['id']) for t in tasks)
                result['medians'].append({'backend': backend, 'kind': kind, 'policy': policy, 'query_ms': 1000 * value})
    write(ROOT / 'verification/BENCHMARK.json', result)
    print(json.dumps(result['medians'], indent=2))


if __name__ == '__main__':
    main()
