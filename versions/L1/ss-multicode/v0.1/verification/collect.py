"""Post-evaluation descriptive aggregation and isolated single-process timing; no policy fitting."""
from collections import Counter
import json
import statistics
import sys
import time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from evaluation.integrity import sha, verify, write
from evaluation.cases import make_case, stream
from evaluation.metrics import metrics, case_probes, subset
from ss_multicode.model import Model, SPECS, decide
from ss_multicode.learning import Learner, teacher
from evaluate import events_for


def main():
    repeat_root = Path(sys.argv[1]).resolve(); repeat = []
    file_set = lambda root: {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name != 'PERFORMANCE.json'}
    assert file_set(ROOT / 'results') == file_set(repeat_root)
    for p in sorted((ROOT / 'results').rglob('*')):
        if p.is_file() and p.name != 'PERFORMANCE.json':
            rel = p.relative_to(ROOT / 'results'); h = sha(p); other = sha(repeat_root / rel); assert h == other
            repeat.append({'file': rel.as_posix(), 'sha256': h, 'repeat_sha256': other})
    write(ROOT / 'verification/REPEATABILITY.json', {'freeze_hash': verify(), 'all_equal': True, 'files': repeat, 'excluded': ['PERFORMANCE.json']})
    baseline = json.loads((ROOT / 'verification/BASELINE.json').read_text(encoding='utf-8'))
    changed = [n for n, h in baseline['previous_files'].items() if sha(ROOT.parent / n) != h]; assert not changed
    write(ROOT / 'verification/PRESERVATION.json', {'previous_files': len(baseline['previous_files']), 'all_unchanged': True, 'changed': changed})
    result = json.loads((ROOT / 'results/EVALUATION.json').read_text(encoding='utf-8'))
    snapshots = {}; forgetting = {}; gates = {}; costs = {}; blocks = {}; pooled = {}; pairs = []; correlations = []
    cases = {c['seed']: c for c in json.loads((ROOT / 'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
    with np.load(ROOT / 'results/SCORES.npz', allow_pickle=False) as z:
        for run in result['runs']:
            head = (run['scenario'], run['architecture'])
            for p, bs in run['blocks'].items():
                for b in bs: blocks.setdefault(head + (p, b['phase'], b['epoch']), Counter()).update(b['metrics'])
            case = cases[run['data_seed']]; events = events_for(case, run['scenario'])
            for s in run['snapshots']:
                for p, info in s['metrics'].items():
                    key = head + (p, s['phase'], s['epoch'])
                    for g, m in info['groups'].items(): snapshots.setdefault(key + (g,), Counter()).update(m)
                    forgetting.setdefault(key, Counter()).update({k: v for k, v in info['forgetting'].items() if type(v) is int})
                    gates.setdefault(key, Counter()).update(info['versus_mean'])
                costs.setdefault(head + (s['phase'], s['epoch']), []).append(s['storage'])
                if s['epoch'] == 4 and s['phase'] in ('A', 'B', 'C'):
                    raw = {k: z[s['prefix'] + '_' + k] for k in ('readers', 'checker')}
                    _, mask, truth = case_probes(case, {e['id'] for e in events[:s['step']]})
                    ix = np.flatnonzero(mask | (np.arange(320) >= 192))
                    for p, acceptance in run['policies'].items():
                        pooled.setdefault(head + (p,), Counter()).update(metrics(subset(raw, ix), acceptance, mask[ix], truth[ix]))
                if s['phase'] == 'C' and s['epoch'] == 4:
                    raw = {k: z[s['prefix'] + '_' + k] for k in ('readers', 'checker')}
                    flattened = raw['readers'][192:].transpose(1, 0, 2).reshape(raw['readers'].shape[1], -1)
                    if len(flattened) > 1:
                        correlations.append({'data_seed': run['data_seed'], 'scenario': run['scenario'], 'architecture': run['architecture'], 'seed': run['seed'],
                            'unknown_query_label_score_correlation': np.corrcoef(flattened).tolist(),
                            'scope': 'Correlations over128 query*4 candidate scores. Not independence proof or independent datasets.'})
            if run['architecture'] not in ('single512', 'exact'):
                ref = next(r for r in result['runs'] if r['architecture'] == 'single512' and all(run[k] == r[k] for k in ('data_seed', 'scenario', 'seed')))
                a = next(s for s in ref['snapshots'] if s['phase'] == 'C' and s['epoch'] == 4)
                b = next(s for s in run['snapshots'] if s['phase'] == 'C' and s['epoch'] == 4)
                ar = {k: z[a['prefix'] + '_' + k] for k in ('readers', 'checker')}; br = {k: z[b['prefix'] + '_' + k] for k in ('readers', 'checker')}
                truth = np.array([int(r['label']) for g in ('A', 'B', 'C') for r in case['groups'][g]])
                for pn in ('mean', 'calibrated'):
                    av = decide(ar, ref['policies'][pn])['accepted']; bv = decide(br, run['policies'][pn])['accepted']; transitions = Counter()
                    for i, target in enumerate(truth):
                        status = lambda v: 'correct' if v == target else 'abstain' if v < 0 else 'wrong'
                        transitions[status(av[i]) + '_to_' + status(bv[i])] += 1
                    for i in range(192, 320): transitions['unknown_' + ('accept' if av[i] >= 0 else 'reject') + '_to_' + ('accept' if bv[i] >= 0 else 'reject')] += 1
                    pairs.append({'data_seed': run['data_seed'], 'scenario': run['scenario'], 'architecture': run['architecture'], 'seed': run['seed'], 'policy': pn, 'versus': 'single512', 'counts': dict(transitions)})
    fields = ('scenario', 'architecture', 'policy', 'phase', 'epoch')
    summary = {'trajectories': len(result['runs']), 'teacher_presentations': sum(r['teacher_presentations'] for r in result['runs']),
               'snapshots': [dict(zip(fields + ('group',), k), **v) for k, v in snapshots.items()],
               'forgetting': [dict(zip(fields, k), **v) for k, v in forgetting.items()],
               'gates': [dict(zip(fields, k), **v) for k, v in gates.items()],
               'blocks': [dict(zip(fields, k), **v) for k, v in blocks.items()],
               'pooled_A4_B4_C4': [dict(zip(fields[:3], k), **v) for k, v in pooled.items()],
               'costs': [dict(zip(('scenario', 'architecture', 'phase', 'epoch'), k),
                         **{n: {'min': min(s[n] for s in v), 'median': statistics.median(s[n] for s in v), 'max': max(s[n] for s in v)}
                            for n in ('coefficient_bytes', 'warm_atom_bytes', 'metadata_utf8_bytes', 'exact_entries', 'reader_vector_updates', 'pair_vector_updates', 'reader_coefficient_update_elements', 'pair_correlation_elements')}) for k, v in costs.items()]}
    write(ROOT / 'verification/SUMMARY.json', summary)
    write(ROOT / 'verification/PAIRED_C4.json', {'scope': 'Descriptive paired outcomes at C4; frozen policies, no test-selected tuning.', 'rows': pairs})
    write(ROOT / 'verification/CODE_CORRELATIONS.json', {'rows': correlations})
    # Sequential benchmark after the two full evaluations, no competing experiment subprocesses.
    cal = json.loads((ROOT / 'evaluation/CALIBRATION.json').read_text(encoding='utf-8'))
    benchmark_case = make_case('multi-benchmark'); events = events_for(benchmark_case, 'clean')[:256]
    queries = [r['context'] for g in ('A', 'B', 'C') for r in benchmark_case['groups'][g]] + benchmark_case['unknown']
    bench = []
    for arch in SPECS:
        times = []; query_times = []
        for _ in range(3):
            s = Learner(Model(arch, 'code-benchmark', acceptance=cal['selected'][arch]['policy'])); start = time.perf_counter()
            for e in events:
                req = s.question(e['context'])['request']; s = s.answer(req, teacher(req, e['teacher_label']))
            times.append(time.perf_counter() - start)
            s.model.predict(queries)  # warm batch
            tic = time.perf_counter(); s.model.predict(queries); query_times.append(time.perf_counter() - tic)
        bench.append({'architecture': arch, 'teachers': len(events), 'teacher_seconds': times,
                      'median_ms_per_teacher': statistics.median(times) / len(events) * 1000,
                      'queries': len(queries), 'query_seconds': query_times,
                      'median_ms_per_query_in_batch320': statistics.median(query_times) / len(queries) * 1000,
                      'storage_after256': s.storage()})
    write(ROOT / 'verification/BENCHMARK.json', {'scope': 'One process, three fresh runs, independent data. Transactions include request, validation, fingerprints, copies and update. Query is batch320. Not peak RSS, pure kernel, energy or equal FLOPs.', 'rows': bench})
    ex = ROOT / 'examples'; ex.mkdir()
    s = Learner.load(ROOT / 'results/checked-A'); event = events_for(cases['multi-final-0'], 'clean')[256]
    req = s.question(event['context'])['request']; fb = teacher(req, event['teacher_label']); new = s.answer(req, fb)
    write(ex / 'context.json', event['context']); write(ex / 'queries.json', [event['context']]); write(ex / 'request.json', req); write(ex / 'feedback.json', fb)
    write(ex / 'EXPECTED.json', {'note': 'Artificial external teacher, not authentication or model-generated truth.',
                                'before': s.model.predict([event['context']])[0], 'after': new.model.predict([event['context']])[0], 'next_fingerprint': new.fingerprint})
    print(json.dumps({'equal_files': len(repeat), 'previous_unchanged': len(baseline['previous_files']), 'trajectories': len(result['runs'])}), flush=True)
    for row in summary['snapshots']:
        if row['scenario'] == 'clean' and row['phase'] == 'C' and row['epoch'] == 4 and row['group'] in ('A', 'never_taught'):
            print(json.dumps(row), flush=True)


if __name__ == '__main__': main()
