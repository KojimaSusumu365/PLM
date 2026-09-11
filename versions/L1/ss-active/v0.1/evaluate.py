import argparse
import hashlib
import itertools
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_multicode.model import Model, policy
from ss_multicode.learning import Learner, teacher
from ss_active.session import Session, feedback
from evaluation.cases import teaching, truth_map, validate
from evaluation.metrics import probe_context, summarize
from evaluation.integrity import ROOT, verify, write


def teach_events(learner, events):
    for e in events:
        q = learner.question(e['context'])['request']; learner = learner.answer(q, teacher(q, e['label']))
    return learner


def run(base, case, scenario, strategy, acquisition_seed, arrays, out, save):
    session = Session(base, case['pool'], strategy, acquisition_seed); truth = truth_map(case, scenario)
    contexts = [r['context'] for r in probe_context(case)]
    baseline = base.model.raw(contexts)['readers']; corrected = []; trace = []; checkpoints = []
    before = []; after = []; logical_scored = 0; selection_seconds = 0.; response_seconds = 0.; challenge_seconds = 0.
    result = {'data_seed': case['seed'], 'size': case['size'], 'code_seed': base.model.seed, 'scenario': scenario,
              'strategy': strategy, 'acquisition_seed': acquisition_seed, 'base_fingerprint': base.fingerprint,
              'original_pool_digest': digest(session.pool), 'saved': {}}
    challenge = teaching(case, 'D', 2); start = time.perf_counter()
    for budget in (0, 4, 16, 32):
        while len(session.acquired) < budget:
            tic = time.perf_counter(); req = session.ask(); selection_seconds += time.perf_counter()-tic
            selected = req['selection']; context = selected['context']; key = selected['selected_id']; label = truth[key]
            raw_before = session.learner.model.raw([context])['readers'][0]; pred_before = session.learner.model.predict([context])[0]
            tic = time.perf_counter(); new = session.answer(req, feedback(req, label)); response_seconds += time.perf_counter()-tic
            raw_after = new.learner.model.raw([context])['readers'][0]; pred_after = new.learner.model.predict([context])[0]
            if pred_before['tentative'] is not None and pred_before['tentative'] != label and pred_after['tentative'] == label: corrected.append(key)
            logical_scored += selected['diagnostics']['contexts_scored_this_call']
            trace.append({'request': req, 'teacher_label': label, 'truth': label,
                          'before': {k: pred_before[k] for k in ('tentative','accepted')},
                          'after': {k: pred_after[k] for k in ('tentative','accepted')}, 'next_session_fingerprint': new.fingerprint})
            before.append(raw_before); after.append(raw_after); session = new
        scores = session.learner.model.raw(contexts)['readers']; key = f'p{len(arrays):05d}'; arrays[key] = scores
        pre = {'budget': budget, 'stage': 'after_acquisition', 'array': key, 'learner_step': session.learner.step,
               'metrics': summarize(scores, case, scenario, session.acquired, False, baseline, scores, corrected),
               'session_fingerprint': session.fingerprint, 'model_fingerprint': session.learner.model.fingerprint,
               'resources': session.learner.storage() | {'remaining_pool': len(session.pool), 'acquired': budget,
                   'session_json_bytes': len(json.dumps(session.state, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8')),
                   'logical_selection_contexts_scored': logical_scored}}
        checkpoints.append(pre)
        prefix = f's{case["size"]}-{strategy}-b{budget}'
        if save:
            session.save(out/prefix); result['saved'][prefix] = {'kind': 'session', 'budget': budget, 'fingerprint': session.fingerprint}
        tic = time.perf_counter(); challenged = teach_events(session.learner, challenge); challenge_seconds += time.perf_counter()-tic
        post_scores = challenged.model.raw(contexts)['readers']; key = f'p{len(arrays):05d}'; arrays[key] = post_scores
        checkpoints.append({'budget': budget, 'stage': 'after_challenge', 'array': key, 'learner_step': challenged.step,
                            'metrics': summarize(post_scores, case, scenario, session.acquired, True, baseline, scores, corrected),
                            'model_fingerprint': challenged.model.fingerprint, 'resources': challenged.storage()})
        if save:
            name = prefix+'-post'; challenged.save(out/name); result['saved'][name] = {'kind': 'learner', 'budget': budget, 'fingerprint': challenged.fingerprint}
        assert session.learner.step == base.step+budget  # challenge fork never feeds back into acquisition
    prefix = f't{len(arrays):05d}'
    arrays[prefix+'_before'] = np.array(before); arrays[prefix+'_after'] = np.array(after)
    result.update({'trace': trace, 'trace_prefix': prefix, 'checkpoints': checkpoints,
                   'acquired_ids': session.acquired, 'final_session_fingerprint': session.fingerprint,
                   'challenge_teacher_digest': digest([(e['id'],e['label']) for e in challenge]),
                   'acquisition_teachers': len(trace), 'challenge_teachers': 4*len(challenge),
                   'checks': {'no_repeated_acquisition': len(set(session.acquired)) == len(trace) == 32,
                              'pool_only': set(session.acquired) <= {r['id'] for r in case['pool']},
                              'future_D_and_unknown_not_selected': not set(session.acquired) & {r['id'] for r in case['groups']['D']},
                              'correct_teacher_only': all(r['teacher_label'] == truth[r['request']['selection']['selected_id']] for r in trace),
                              'base_immutable': base.fingerprint == result['base_fingerprint']}})
    assert all(result['checks'].values())
    return result, {'total_seconds': time.perf_counter()-start, 'selection_seconds': selection_seconds,
                    'response_seconds_including_selection_revalidation': response_seconds, 'challenge_seconds': challenge_seconds}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); p.add_argument('--development', action='store_true'); a = p.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    data = json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['development' if a.development else 'evaluation']
    codes = ['code-dev'] if a.development else protocol['code_seeds']; acqs = ['acq-dev'] if a.development else protocol['acquisition_seeds']
    result = {'experiment': protocol['experiment'], 'freeze_hash': 'development' if a.development else verify(),
              'bases': [], 'runs': [], 'two_world_first_selection_checks': [], 'eligible_for_inference': False}
    arrays = {}; times = {'environment': {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()}, 'bases': [], 'runs': []}
    for case, code in itertools.product(data, codes):
        assert validate(case)
        initial = teaching(case, 'ABC', 4); tic = time.perf_counter(); base = teach_events(Learner(Model('concat512', code, acceptance=policy())), initial)
        times['bases'].append(time.perf_counter()-tic)
        save = case['seed'] == data[0]['seed'] and code == codes[0]
        descriptor = {'data_seed': case['seed'], 'size': case['size'], 'code_seed': code, 'teachers': len(initial), 'fingerprint': base.fingerprint,
                      'teacher_digest': digest([(e['id'], e['label']) for e in initial])}
        if save:
            name = f'base-s{case["size"]}'; base.save(out/name); descriptor['saved'] = name
        result['bases'].append(descriptor)
        for scenario, acq, strategy in itertools.product(protocol['scenarios'], acqs, protocol['strategies']):
            r, t = run(base, case, scenario, strategy, acq, arrays, out, save and scenario == 'stationary' and acq == acqs[0])
            result['runs'].append(r); times['runs'].append(t)
            print('completed', len(result['runs']), case['seed'], case['size'], code, scenario, acq, strategy, flush=True)
    for r in [r for r in result['runs'] if r['scenario'] == 'stationary']:
        other = next(s for s in result['runs'] if s['scenario'] == 'changed_pool16' and all(r[k] == s[k] for k in ('data_seed','size','code_seed','acquisition_seed','strategy')))
        assert r['trace'][0]['request'] == other['trace'][0]['request']
        result['two_world_first_selection_checks'].append({'data_seed': r['data_seed'], 'size': r['size'], 'code_seed': r['code_seed'], 'acquisition_seed': r['acquisition_seed'], 'strategy': r['strategy'], 'equal': True})
    result['arrays'] = {k: {'shape': list(v.shape), 'sha256': hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()} for k,v in arrays.items()}
    result['actual_teacher_presentations'] = sum(b['teachers'] for b in result['bases']) + sum(r['acquisition_teachers']+r['challenge_teachers'] for r in result['runs'])
    result['all_checks_passed'] = all(all(r['checks'].values()) for r in result['runs']); assert result['all_checks_passed']
    result['result_digest'] = digest(result)
    write(out/'EVALUATION.json', result); write(out/'PERFORMANCE.json', times); np.savez_compressed(out/'SCORES.npz', **arrays)
    print(json.dumps({'trajectories': len(result['runs']), 'teachers': result['actual_teacher_presentations'], 'arrays': len(arrays), 'digest': result['result_digest']}), flush=True)


if __name__ == '__main__': main()
