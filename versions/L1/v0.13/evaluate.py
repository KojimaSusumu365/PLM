import argparse
import copy
import hashlib
import itertools
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
from plm_l1_v013.algebra import canonical, digest
from plm_l1_v013.teaching import Session
from evaluation.cases import disjoint, queries
from evaluation.integrity import ROOT, verify_freeze
from evaluation.metrics import measure


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def knowledge_fingerprint(model):
    return digest([model.config, model.meta['members'], [hashlib.sha256(m['weights'].astype('<c16').tobytes()).hexdigest() for m in model.members]])


def snapshot(task, session, budget, prepared):
    model = session.model
    qs = [q for _, group in prepared for q in group]
    answers = model.predict_many([q['context'] for q in qs])
    index = 0
    stages = []
    for kind, group in prepared:
        ps = answers[index:index + len(group)]
        index += len(group)
        records = [dict(query_id=canonical(q['context']), allowed=q['allowed'], **p) for q, p in zip(group, ps)]
        stages.append({'kind': kind, 'metrics': measure([p['value'] for p in ps], [q['allowed'] for q in group]), 'predictions': records})
    unknown = {f: 'not-registered' for f in model.config['fields']}
    try:
        model.predict(unknown)
        unknown_rejected = False
    except ValueError as error:
        unknown_rejected = str(error) == 'unknown_field_value'
    return {'budget': budget, 'labels_used': len(session.receipts), 'remaining_pool': len(session.pool),
            'fingerprint': model.fingerprint, 'knowledge_fingerprint': knowledge_fingerprint(model),
            'teacher_set_digest': digest(sorted(session.rows, key=canonical)), 'candidate_masks': [m['mask'] for m in model.members],
            'unknown_values_rejected': unknown_rejected, 'storage': model.storage(), 'stages': stages}


def paired_checks(runs):
    records = []
    for a in [r for r in runs if r['family'] == 'paired_simple']:
        b = next(r for r in runs if r['family'] == 'paired_hidden' and all(r[k] == a[k] for k in ('method', 'dimension', 'code_seed', 'acquisition_seed')))
        ra = a['trace'][0]['request'] if a['trace'] else None
        rb = b['trace'][0]['request'] if b['trace'] else None
        records.append({'method': a['method'], 'dimension': a['dimension'], 'code_seed': a['code_seed'], 'acquisition_seed': a['acquisition_seed'],
                        'initial_model_and_request_equal': a['snapshots'][0]['fingerprint'] == b['snapshots'][0]['fingerprint'] and ra == rb})
    return records


def full_pool_checks(runs):
    records = []
    for active in [r for r in runs if r['method'] == 'all/active']:
        random = next(r for r in runs if r['method'] == 'all/random' and all(r[k] == active[k] for k in ('task_id', 'dimension', 'code_seed', 'acquisition_seed')))
        a, b = active['snapshots'][-1], random['snapshots'][-1]
        full = a['labels_used'] == b['labels_used'] == 16
        records.append({'task_id': active['task_id'], 'dimension': active['dimension'], 'code_seed': active['code_seed'], 'acquisition_seed': active['acquisition_seed'],
                        'both_used_full_pool': full, 'same_final_knowledge': a['knowledge_fingerprint'] == b['knowledge_fingerprint'] if full else None,
                        'same_final_teacher_set': a['teacher_set_digest'] == b['teacher_set_digest'] if full else None})
    return records


def judge(result):
    checks = [{'name': 'split_disjoint', 'kind': 'integrity', 'passed': result['splits_disjoint']},
              {'name': 'label_blind_paired_world', 'kind': 'control', 'passed': all(r['initial_model_and_request_equal'] for r in result['paired_worlds'])},
              {'name': 'full_pool_final_equality', 'kind': 'control', 'passed': all(r['same_final_knowledge'] and r['same_final_teacher_set'] for r in result['full_pool_checks'] if r['both_used_full_pool'])}]
    for i, run in enumerate(result['runs']):
        ids = [r['request']['id'] for r in run['trace']]
        checks.append({'name': f'{i}/unique_teacher_requests', 'kind': 'contract', 'passed': len(ids) == len(set(ids)) and all(r['teacher_answer_from_requested_pool_id'] for r in run['trace'])})
        checks.append({'name': f'{i}/retained_masks_only_shrink', 'kind': 'contract', 'passed': run['masks_monotone'] if run['method'].startswith('all/') else True})
        for snap in run['snapshots']:
            budget = snap['budget']
            checks.append({'name': f'{i}/{budget}/budget', 'kind': 'contract', 'passed': snap['labels_used'] <= budget and snap['labels_used'] + snap['remaining_pool'] == run['initial_pool_size']})
            checks.append({'name': f'{i}/{budget}/candidate_cap', 'kind': 'contract', 'passed': len(snap['candidate_masks']) <= 41})
            checks.append({'name': f'{i}/{budget}/unknown_values', 'kind': 'control', 'passed': snap['unknown_values_rejected']})
            for stage in snap['stages']:
                m = stage['metrics']
                checks.append({'name': f'{i}/{budget}/{stage["kind"]}/accounting', 'kind': 'accounting', 'passed': m['requests'] == m['correct'] + m['wrong'] + m['abstained'] and m['accepted'] == m['correct'] + m['wrong']})
                checks.append({'name': f'{i}/{budget}/{stage["kind"]}/acceptance_contract', 'kind': 'contract', 'passed': all(p['value'] is None or (p['possible_labels'] == [p['value']] and not p['learning_insufficient'] and not p['input_insufficient'] and p['candidate_count'] > 0) for p in stage['predictions'])})
    for i, control in enumerate(result['zero_weight_controls']):
        checks.append({'name': f'{i}/zero_memory', 'kind': 'control', 'passed': all(s['metrics']['accepted'] == 0 for s in control['snapshot']['stages'])})
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--development', action='store_true')
    parser.add_argument('--limit', type=int)
    a = parser.parse_args()
    if a.limit is not None and not a.development:
        raise ValueError('final_evaluation_cannot_be_limited')
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT / 'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    tasks = json.loads((ROOT / 'data' / ('development.json' if a.development else 'evaluation.json')).read_text(encoding='utf-8'))
    if a.limit:
        tasks = tasks[:a.limit]
    result = {'schema': 'plm-v013-evaluation', 'freeze_hash': 'development' if a.development else verify_freeze(),
              'splits_disjoint': all(disjoint(t) for t in tasks), 'runs': [], 'saved_sessions': {}, 'zero_weight_controls': [], 'eligible_for_inference': False}
    performance = {'environment': {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()}, 'runs': []}
    for task in tasks:
        prepared = queries(task)
        for retention, strategy in protocol['methods']:
            configs = [('ss', d, s, acquisition) for d, s, acquisition in itertools.product(protocol['dimensions'], protocol['code_seeds'], protocol['acquisition_seeds'])]
            configs += [('exact', 2048, 'exact', acquisition) for acquisition in protocol['acquisition_seeds']]
            for backend, d, seed, acquisition in configs:
                start = time.perf_counter()
                session = Session(task['initial'], task['pool'], dict(backend=backend, dimension=d, seed=seed, retention=retention))
                fit_time = time.perf_counter() - start
                acquisition_time = evaluation_time = 0.
                run = {'task_id': task['id'], 'family': task['family'], 'method': retention + '/' + strategy, 'backend': backend,
                       'dimension': d if backend == 'ss' else None, 'code_seed': seed, 'acquisition_seed': acquisition,
                       'initial_labels': len(task['initial']), 'initial_pool_size': len(task['pool']), 'trace': [], 'snapshots': [], 'masks_monotone': True}
                stopped = None
                for budget in protocol['budgets']:
                    while len(session.receipts) < budget and stopped is None:
                        started = time.perf_counter()
                        request = session.choose(strategy, acquisition)
                        acquisition_time += time.perf_counter() - started
                        if request.get('status') == 'no_request':
                            stopped = request['reason']
                            break
                        # Broker sees truth; selection receives only the unlabeled pool.
                        answer = task['teacher_answers'][request['id']]
                        before_masks = {tuple(m['mask']) for m in session.model.members}
                        started = time.perf_counter()
                        updated = session.answer(request, answer)
                        fit_time += time.perf_counter() - started
                        after_masks = {tuple(m['mask']) for m in updated.model.members}
                        run['masks_monotone'] &= after_masks <= before_masks
                        run['trace'].append({'step': len(updated.receipts), 'request': request, 'teacher_label': answer,
                                             'teacher_answer_from_requested_pool_id': answer == task['teacher_answers'][request['id']],
                                             'next_model_fingerprint': updated.model.fingerprint,
                                             'candidate_count_before': len(before_masks), 'candidate_count_after': len(after_masks)})
                        session = updated
                    started = time.perf_counter()
                    run['snapshots'].append(snapshot(task, session, budget, prepared))
                    evaluation_time += time.perf_counter() - started
                    if retention == 'all' and strategy == 'active' and backend == 'ss' and d == 2048 and seed == protocol['code_seeds'][0] and acquisition == protocol['acquisition_seeds'][0]:
                        name = f'hidden-b{budget}' if task['family'] == 'paired_hidden' and budget in (0, 1, 4, 16) else 'roles-b16' if task['family'] == 'roles' and budget == 16 else None
                        if name:
                            session.save(out / name)
                            result['saved_sessions'][name] = {'task_id': task['id'], 'budget': budget, 'labels_used': len(session.receipts),
                                                              'fingerprint': session.model.fingerprint, 'settings': session.settings,
                                                              'strategy': strategy, 'acquisition_seed': acquisition}
                        if task['family'] in ('unary', 'xor2', 'and2', 'switch3', 'parity3') and task['id'].endswith('/0') and budget == 0:
                            zero = copy.deepcopy(session)
                            for member in zero.model.members:
                                member['weights'][:] = 0
                            zero.model.refresh()
                            result['zero_weight_controls'].append({'task_id': task['id'], 'snapshot': snapshot(task, zero, 0, prepared)})
                run['stop_reason'] = stopped
                result['runs'].append(run)
                performance['runs'].append({'index': len(result['runs']) - 1, 'fit_and_request_revalidation_seconds': fit_time,
                                            'acquisition_seconds': acquisition_time, 'evaluation_seconds': evaluation_time})
        print('completed', task['id'], 'sessions', len(result['runs']), flush=True)
    result['paired_worlds'] = paired_checks(result['runs'])
    result['full_pool_checks'] = full_pool_checks(result['runs'])
    result['checks'] = judge(result)
    result['all_checks_passed'] = all(c['passed'] for c in result['checks'])
    result['result_digest'] = digest(result)
    write(out / 'EVALUATION.json', result)
    write(out / 'PERFORMANCE.json', performance)
    print(json.dumps({'sessions': len(result['runs']), 'checks': len(result['checks']), 'passed': result['all_checks_passed'], 'digest': result['result_digest']}), flush=True)
    return 0 if result['all_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
