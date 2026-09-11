"""Single-process, posthoc cost diagnostic. No tuning of models or acquisition."""
import json
import platform
import statistics
import sys
import time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from plm_l1_v013.training import fit
from evaluate import write


def main():
    tasks = json.loads((ROOT / 'data/evaluation.json').read_text(encoding='utf-8'))
    tasks = [t for t in tasks if t['id'] in ('evaluation/unary/0', 'evaluation/paired/hidden', 'evaluation/roles/0')]
    records = []
    for task in tasks:
        for backend in ('ss', 'exact'):
            for retention in ('all', 'minimal'):
                for trial in range(3):
                    started = time.perf_counter()
                    model = fit(task['initial'], backend=backend, dimension=2048, seed='evaluation-0', retention=retention)[0]
                    fit_time = time.perf_counter() - started
                    contexts = [r['context'] for r in task['test']]
                    model.predict_many(contexts)
                    started = time.perf_counter()
                    model.predict_many(contexts)
                    batch_time = (time.perf_counter() - started) / len(contexts)
                    started = time.perf_counter()
                    for context in contexts:
                        model.predict(context)
                    scalar_time = (time.perf_counter() - started) / len(contexts)
                    acquisition = {}
                    for strategy in ('active', 'random'):
                        model.select(task['pool'], strategy)
                        started = time.perf_counter()
                        for _ in range(3):
                            model.select(task['pool'], strategy)
                        acquisition[strategy] = (time.perf_counter() - started) / 3
                    records.append({'task_id': task['id'], 'backend': backend, 'retention': retention, 'trial': trial,
                                    'fit_seconds': fit_time, 'batch_query_seconds_per_request': batch_time, 'scalar_query_seconds_per_request': scalar_time,
                                    'acquisition_seconds_per_pool': acquisition, 'storage': model.storage()})
    medians = []
    for backend in ('ss', 'exact'):
        for retention in ('all', 'minimal'):
            rows = [r for r in records if r['backend'] == backend and r['retention'] == retention]
            def median(fn):
                return statistics.median(statistics.median(fn(r) for r in rows if r['task_id'] == task['id']) for task in tasks)
            medians.append({'backend': backend, 'retention': retention, 'fit_ms': 1000 * median(lambda r: r['fit_seconds']),
                            'batch_query_ms': 1000 * median(lambda r: r['batch_query_seconds_per_request']),
                            'scalar_query_ms': 1000 * median(lambda r: r['scalar_query_seconds_per_request']),
                            'active_select_ms': 1000 * median(lambda r: r['acquisition_seconds_per_pool']['active']),
                            'random_select_ms': 1000 * median(lambda r: r['acquisition_seconds_per_pool']['random'])})
    result = {'scope': 'Single process after both final runs. Three prelisted task initial states, D2048/first code seed, 3 repeats. Warm atoms. Scalar query and batched query reported separately. Acquisition over16 unlabeled contexts. Not whole language, total RAM, maximum41-candidate stress, or energy.',
              'environment': {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()}, 'rows': records, 'medians': medians}
    write(ROOT / 'verification/BENCHMARK.json', result)
    print(json.dumps(medians, indent=2))


if __name__ == '__main__':
    main()
