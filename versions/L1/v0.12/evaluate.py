import argparse
import copy
import itertools
import json
import platform
import random
import sys
import time
import zipfile
from pathlib import Path
import numpy as np
from plm_l1_v011.algebra import canonical, digest
from plm_l1_v012.core import POLICIES
from plm_l1_v012.training import train_model
from plm_l1_v012.evidence import build_evidence
from evaluation.cases import query_stages
from evaluation.integrity import ROOT, verify_freeze
from evaluation.metrics import measure, equal_count


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def disjoint(task):
    sets = [{canonical(r['context']) for r in task[n]} for n in ('train', 'selection', 'calibration', 'test')]
    if 'added' in task:
        sets.append({canonical(r['context']) for r in task['added']})
    return not any(a & b for a, b in itertools.combinations(sets, 2))


def evaluate_model(task, model, two_missing=False):
    stages = []
    timing = {p: 0. for p in POLICIES}
    for kind, queries in query_stages(task, two_missing):
        predictions = []
        for query in queries:
            outcomes = {}
            for policy in POLICIES:
                start = time.perf_counter()
                try:
                    out = model.predict(query['context'], policy=policy)
                except ValueError as error:
                    if str(error) not in ('unknown_field_value', 'unknown_context_fields'):
                        raise
                    out = {'value': None, 'status': 'abstain', 'reason': str(error), 'confidence': 0., 'completion_count': 0, 'evidence': []}
                timing[policy] += time.perf_counter() - start
                outcomes[policy] = {k: out[k] for k in ('value', 'reason', 'confidence', 'completion_count', 'evidence')}
            predictions.append({'query_id': canonical(query['context']), 'allowed': query['allowed'], 'outcomes': outcomes})
        metrics = {p: measure([q['outcomes'][p]['value'] for q in predictions], [q['allowed'] for q in predictions]) for p in POLICIES}
        transitions = {}
        for policy in POLICIES[1:]:
            removed = [q for q in predictions if q['outcomes']['baseline']['value'] is not None and q['outcomes'][policy]['value'] is None]
            transitions[policy] = {'vetoed_correct': sum(len(q['allowed']) == 1 and q['outcomes']['baseline']['value'] == q['allowed'][0] for q in removed),
                                   'vetoed_wrong': sum(not (len(q['allowed']) == 1 and q['outcomes']['baseline']['value'] == q['allowed'][0]) for q in removed)}
        matched = equal_count([{'method': p, 'predictions': [dict(query_id=q['query_id'], allowed=q['allowed'], gated=q['outcomes'][p]['value']) for q in predictions]} for p in POLICIES])
        stages.append({'kind': kind, 'metrics': metrics, 'transitions': transitions, 'matched_coverage': matched, 'predictions': predictions})
    return stages, timing


def stress(protocol):
    rows = []
    keys = list(itertools.product('01', repeat=6))
    random.Random('v012-witness-load').shuffle(keys)
    for load in protocol['witness_loads']:
        train = [{'context': dict(zip(('a', 'b', 'c', 'd', 'e', 'f'), k)), 'label': str(i % 2)} for i, k in enumerate(keys[:load])]
        for backend in ('ss', 'exact'):
            configs = itertools.product(protocol['dimensions'], protocol['seeds']) if backend == 'ss' else [(0, 'exact')]
            for d, seed in configs:
                m = build_evidence(train, list('abcdef'), ['0', '1'], d, seed, backend)
                predictions = []
                for i, k in enumerate(keys):
                    context = dict(zip('abcdef', k))
                    scores = m.scores(context)
                    hits = [y for y, s in zip(m.labels, scores) if s >= .5]
                    predictions.append({'key': ''.join(k), 'known': i < load, 'expected': str(i % 2) if i < load else None,
                                        'hits': hits, 'scores': [float(s) for s in scores]})
                rows.append({'load': load, 'backend': backend, 'dimension': d, 'seed': seed,
                             'known_unique_correct': sum(p['known'] and p['hits'] == [p['expected']] for p in predictions),
                             'known_wrong_label_hit': sum(p['known'] and any(y != p['expected'] for y in p['hits']) for p in predictions),
                             'unknown_any_support': sum(not p['known'] and bool(p['hits']) for p in predictions),
                             'unknown_unique_support': sum(not p['known'] and len(p['hits']) == 1 for p in predictions),
                             'predictions': predictions})
    return rows


def compare_v011(result):
    with zipfile.ZipFile(ROOT / 'vendor/PLM-L1-v0.11.zip') as z:
        old = json.loads(z.read('PLM-L1-v0.11/results/EVALUATION.json'))
    old_lookup = {(r['task_id'], r['after'], r['method'], r['dimension'], r['seed']): r for r in old['runs'] if r['enabled'] and r['budget'] == 'per_candidate'}
    records = []
    for run in result['runs']:
        if run['category'] not in ('regression', 'selection_off'):
            continue
        key = (run['task_id'], run['after'], run['method'], run['dimension'], run['seed'])
        prior = old_lookup[key]
        matched = run['base_fingerprint'] == prior['fingerprint']
        probes = 0
        for stage in run['stages']:
            previous = next(s for s in prior['stages'] if s['kind'] == stage['kind'])
            pairs = [(p['query_id'], p['allowed'], p['outcomes']['baseline']['value']) for p in stage['predictions']]
            before = [(p['query_id'], p['allowed'], p['gated']) for p in previous['predictions']]
            matched &= pairs == before
            probes += len(pairs)
        records.append({'task_id': run['task_id'], 'method': run['method'], 'dimension': run['dimension'], 'seed': run['seed'],
                        'after': run['after'], 'same_base_fingerprint_and_decisions': matched, 'probes': probes})
    return records


def judge(result):
    checks = [{'name': 'splits_disjoint', 'passed': result['splits_disjoint'], 'kind': 'integrity'},
              {'name': 'prior_baselines_equal', 'passed': all(r['same_base_fingerprint_and_decisions'] for r in result['v011_comparison']), 'kind': 'regression'},
              {'name': 'indistinguishable_worlds', 'passed': all(r['identical_learned_model_and_predictions'] for r in result['paired_worlds']), 'kind': 'control'}]
    for index, run in enumerate(result['runs']):
        for stage in run['stages']:
            for policy, metrics in stage['metrics'].items():
                ok = metrics['requests'] == metrics['correct'] + metrics['wrong'] + metrics['abstained'] and metrics['accepted'] == metrics['correct'] + metrics['wrong']
                checks.append({'name': f'{index}/{stage["kind"]}/{policy}/accounting', 'passed': ok, 'kind': 'accounting'})
            subset = all(q['outcomes'][p]['value'] in (None, q['outcomes']['baseline']['value']) for q in stage['predictions'] for p in POLICIES)
            checks.append({'name': f'{index}/{stage["kind"]}/veto_only', 'passed': subset, 'kind': 'contract'})
            certified = all(q['outcomes']['completion']['completion_count'] <= 256 and
                            all(not e[k] for e in q['outcomes']['completion']['evidence'] for k in ('prediction_abstentions', 'prediction_disagreements', 'missing_witnesses', 'conflicting_witnesses'))
                            for q in stage['predictions'] if q['outcomes']['completion']['value'] is not None)
            checks.append({'name': f'{index}/{stage["kind"]}/all_branches_supported', 'passed': certified, 'kind': 'contract'})
    for i, control in enumerate(result['zero_witness_controls']):
        checks.append({'name': f'{i}/zero_witness', 'passed': all(s['metrics']['completion']['accepted'] == 0 for s in control['stages']), 'kind': 'control'})
    for i, row in enumerate(result['witness_stress']):
        if row['backend'] == 'exact':
            checks.append({'name': f'{i}/exact_support', 'passed': row['known_unique_correct'] == row['load'] and row['unknown_any_support'] == 0, 'kind': 'control'})
    return checks


def paired_world_audit(runs):
    paired = [r for r in runs if r['family'] == 'unseen_interaction']
    records = []
    for simple in [r for r in paired if r['task_id'].endswith('/simple')]:
        hidden = next(r for r in paired if r['task_id'].endswith('/hidden') and all(r[k] == simple[k] for k in ('method', 'dimension', 'seed')))
        def decisions(run):
            return [(s['kind'], q['query_id'], [q['outcomes'][p]['value'] for p in POLICIES]) for s in run['stages'] for q in s['predictions']]
        records.append({'method': simple['method'], 'dimension': simple['dimension'], 'seed': simple['seed'],
                        'identical_learned_model_and_predictions': simple['fingerprint'] == hidden['fingerprint'] and decisions(simple) == decisions(hidden)})
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--development', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.limit is not None and not args.development:
        raise ValueError('final_evaluation_cannot_be_limited')
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT / 'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    current = json.loads((ROOT / 'data' / ('development.json' if args.development else 'evaluation.json')).read_text(encoding='utf-8'))
    old = json.loads((ROOT / 'data/v011-regression.json').read_text(encoding='utf-8'))
    jobs = [('new_partition', t, 'hybrid3', 'validation') for t in current]
    if args.limit:
        jobs = jobs[:args.limit]
    if not args.development:
        jobs = [('regression', t, rep, 'validation') for t in old for rep in ('hybrid3', 'product')] + jobs
        jobs += [('selection_off', t, 'hybrid3', 'off') for t in old if t['family'] in ('unary', 'xor2', 'and2') and t['id'].endswith('/0')]
    result = {'schema': 'plm-v012-evaluation', 'freeze_hash': 'development' if args.development else verify_freeze(),
              'splits_disjoint': all(disjoint(t) for _, t, _, _ in jobs), 'runs': [], 'saved_models': {},
              'zero_witness_controls': [], 'eligible_for_inference': False}
    performance = {'environment': {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()}, 'runs': []}
    for category, task, representation, selector in jobs:
        for after in ((False, True) if 'added' in task else (False,)):
            for backend in protocol['backends']:
                configs = itertools.product(protocol['dimensions'], protocol['seeds']) if backend == 'ss' else [(2048, 'exact-kernel')]
                for dimension, seed in configs:
                    train = task['train'] + (task['added'] if after else [])
                    model, audit, perf = train_model(train, task['selection'], task['calibration'], representation=representation,
                                                   selector=selector, backend=backend, dimension=dimension, seed=seed)
                    stages, timing = evaluate_model(task, model, category == 'new_partition')
                    result['runs'].append({'category': category, 'task_id': task['id'], 'family': task['family'], 'after': after,
                                           'method': '/'.join((representation, selector, backend)), 'dimension': dimension if backend == 'ss' else None,
                                           'seed': seed, 'base_fingerprint': model.base.fingerprint, 'fingerprint': model.fingerprint,
                                           'audit': audit, 'storage': model.storage(), 'calibration': model.base.calibration, 'stages': stages})
                    performance['runs'].append({'index': len(result['runs']) - 1, **perf, 'policy_query_seconds': timing})
                    if category == 'regression' and representation == 'hybrid3' and backend == 'ss' and dimension == 2048 and seed == protocol['seeds'][0]:
                        name = ('and2' if task['id'].endswith('/and2/0') else 'roles' if task['family'] == 'roles' else 'ambiguity-after' if after else 'ambiguity-before') if task['family'] in ('and2', 'roles', 'ambiguity') else None
                        if task['family'] in ('and2', 'ambiguity') and not task['id'].endswith('/0'):
                            name = None
                        if name:
                            model.save(out / name)
                            result['saved_models'][name] = {'task_id': task['id'], 'after': after, 'fingerprint': model.fingerprint}
                        if task['family'] in ('unary', 'xor2', 'and2', 'switch3', 'parity3') and task['id'].endswith('/0'):
                            zero = copy.deepcopy(model)
                            for evidence in zero.evidence:
                                evidence.weights[:] = 0
                            zero.refresh()
                            zero_stages, _ = evaluate_model(task, zero)
                            result['zero_witness_controls'].append({'task_id': task['id'], 'fingerprint': zero.fingerprint, 'stages': zero_stages})
        print('completed', category, task['id'], representation, 'models', len(result['runs']), flush=True)
    result['witness_stress'] = stress(protocol['stress'])
    result['v011_comparison'] = compare_v011(result) if not args.development else []
    result['paired_worlds'] = paired_world_audit(result['runs'])
    result['checks'] = judge(result)
    result['all_checks_passed'] = all(c['passed'] for c in result['checks'])
    result['result_digest'] = digest(result)
    write(out / 'EVALUATION.json', result)
    write(out / 'PERFORMANCE.json', performance)
    print(json.dumps({'models': len(result['runs']), 'checks': len(result['checks']), 'passed': result['all_checks_passed'], 'digest': result['result_digest']}), flush=True)
    return 0 if result['all_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
