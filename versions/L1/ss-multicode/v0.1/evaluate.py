import argparse
import hashlib
import itertools
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
from ss_multicode.model import Model
from ss_multicode.learning import Learner, teacher
from ss_multicode.algebra import digest
from evaluation.cases import stream, validate
from evaluation.metrics import case_probes, fixed_policies, snapshot_summary, trace_summary
from evaluation.integrity import ROOT, write, verify


def events_for(case, scenario):
    return [dict(e, phase=b['phase'], epoch=b['epoch']) for b in stream(case, scenario) for e in b['events']]


def run(case, scenario, architecture, seed, acceptance, arrays, out, saving):
    policies = fixed_policies(architecture) | {'calibrated': acceptance}
    learner = Learner(Model(architecture, seed, acceptance=acceptance)); known = set(); anchors = {}
    result = {'data_seed': case['seed'], 'scenario': scenario, 'architecture': architecture, 'seed': seed,
              'policies': policies, 'snapshots': [], 'saved': {}}
    start = time.perf_counter(); teacher_seconds = 0.; events = events_for(case, scenario)
    def snapshot(phase, epoch):
        rows, _, _ = case_probes(case, known, phase == 'drift')
        raw = learner.model.raw([r['context'] for r in rows]); prefix = f'p{len(arrays):05d}'
        for key, values in raw.items(): arrays[prefix + '_' + key] = values
        result['snapshots'].append({'phase': phase, 'epoch': epoch, 'step': learner.step, 'prefix': prefix,
            'metrics': snapshot_summary(raw, policies, case, known, phase, epoch, anchors), 'storage': learner.storage()})
    snapshot('initial', 0); before = {'readers': [], 'checker': []}; after = {'readers': [], 'checker': []}
    offset = 0
    for block in stream(case, scenario):
        phase = block['phase']; epoch = block['epoch']
        if phase == 'drift' and epoch == 1: snapshot('drift', 0)
        for event in block['events']:
            raw = learner.model.raw([event['context']])
            for k in raw: before[k].append(raw[k][0])
            tic = time.perf_counter()
            req = learner.question(event['context'])['request']; learner = learner.answer(req, teacher(req, event['teacher_label']))
            teacher_seconds += time.perf_counter() - tic
            known.add(event['id']); offset += 1
            raw = learner.model.raw([event['context']])
            for k in raw: after[k].append(raw[k][0])
        snapshot(phase, epoch)
        if saving and (phase, epoch) in (('A', 4), ('C', 4), ('drift', 4)):
            name = architecture + '-' + phase; learner.save(out / name)
            result['saved'][name] = {'step': learner.step, 'fingerprint': learner.fingerprint}
    before = {k: np.array(v) for k, v in before.items()}; after = {k: np.array(v) for k, v in after.items()}
    prefix = f't{len(arrays):05d}'
    for stage, raw in (('before', before), ('after', after)):
        for key, values in raw.items(): arrays[prefix + '_' + stage + '_' + key] = values
    result['trace_prefix'] = prefix; result['blocks'] = trace_summary(before, after, events, policies)
    result['teacher_sequence_digest'] = digest([(e['id'], e['teacher_label']) for e in events])
    result['teacher_presentations'] = learner.step; result['final_fingerprint'] = learner.fingerprint
    result['checks'] = {'teachers896': learner.step == 896, 'unique_keys192': len(known) == 192,
                        'noise_count': sum(e['teacher_label'] != e['truth'] for e in events) == (8 if scenario == 'noisy_first' else 0),
                        'no_replay': learner.storage()['replay_entries'] == 0,
                        'no_ss_key_table': architecture == 'exact' or not learner.model.entries}
    assert all(result['checks'].values())
    return result, {'total_seconds': time.perf_counter() - start, 'teacher_transaction_seconds': teacher_seconds}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); a = p.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT / 'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    calibration = json.loads((ROOT / 'evaluation/CALIBRATION.json').read_text(encoding='utf-8'))
    cases = json.loads((ROOT / 'data/CASES.json').read_text(encoding='utf-8'))['evaluation']
    assert all(validate(c) for c in cases)
    arrays = {}; result = {'experiment': protocol['experiment'], 'freeze_hash': verify(), 'calibration_digest': calibration['digest'],
                           'runs': [], 'teacher_equality': [], 'eligible_for_inference': False}
    times = {'environment': {'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()}, 'runs': []}
    for case, scenario in itertools.product(cases, protocol['scenarios']):
        configs = list(itertools.product(protocol['architectures'], protocol['code_seeds'])) + [('exact', 'exact')]
        seq = None
        for architecture, seed in configs:
            saving = case == cases[0] and scenario == 'clean' and (seed == protocol['code_seeds'][0] or architecture == 'exact')
            r, timing = run(case, scenario, architecture, seed, calibration['selected'][architecture]['policy'], arrays, out, saving)
            seq = seq or r['teacher_sequence_digest']; assert seq == r['teacher_sequence_digest']
            result['runs'].append(r); times['runs'].append(timing)
            print('completed', len(result['runs']), case['seed'], scenario, architecture, seed, flush=True)
        result['teacher_equality'].append({'data_seed': case['seed'], 'scenario': scenario, 'equal': True, 'digest': seq})
    result['arrays'] = {k: {'shape': list(v.shape), 'sha256': hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()} for k, v in arrays.items()}
    result['all_checks_passed'] = all(all(r['checks'].values()) for r in result['runs']); assert result['all_checks_passed']
    result['result_digest'] = digest(result)
    write(out / 'EVALUATION.json', result); write(out / 'PERFORMANCE.json', times); np.savez_compressed(out / 'SCORES.npz', **arrays)
    print(json.dumps({'trajectories': len(result['runs']), 'teachers': sum(r['teacher_presentations'] for r in result['runs']),
                      'raw_arrays': len(arrays), 'digest': result['result_digest']}), flush=True)


if __name__ == '__main__': main()
