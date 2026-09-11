"""Integrity, aggregate recomputation, isolated training and prediction-only checks."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_multicode.model import Model, SPECS
from ss_multicode.learning import Learner, teacher
from evaluation.integrity import ROOT, sha, verify, write
from evaluation.metrics import snapshot_summary, trace_summary, calibration_rows
from evaluate import events_for


def command(args, cwd, log, accepted=(0,)):
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    p = subprocess.run([sys.executable, '-B', *args], cwd=cwd, env=env, text=True, encoding='utf-8', capture_output=True, timeout=180)
    with log.open('x', encoding='utf-8') as f: f.write(p.stdout + p.stderr)
    assert p.returncode in accepted, (log.name, p.stderr[-2000:])
    return p.stdout, p.stderr


def verify_calibration():
    cal = json.loads((ROOT / 'evaluation/CALIBRATION.json').read_text(encoding='utf-8')); claimed = cal.pop('digest')
    assert digest(cal) == claimed
    assert json.loads((ROOT / 'verification/development/CALIBRATION.json').read_text(encoding='utf-8')) == dict(cal, digest=claimed)
    data = json.loads((ROOT / 'data/CASES.json').read_text(encoding='utf-8'))
    assert set(cal['data_seeds']) == {c['seed'] for c in data['development']}
    assert not set(cal['data_seeds']) & {c['seed'] for c in data['evaluation']}
    with np.load(ROOT / 'verification/development/SCORES.npz', allow_pickle=False) as z:
        for architecture in SPECS:
            records = [{'raw': {k: z[r['prefix'] + '_' + k] for k in ('readers', 'checker')},
                        'known': r['known'], 'truth': r['truth']} for r in cal['records'] if r['architecture'] == architecture]
            rows, best = calibration_rows(architecture, records)
            assert rows == cal['grid'][architecture] and best == cal['selected'][architecture]
    return claimed, sum(len(rows) for rows in cal['grid'].values())


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); a = p.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=False)
    frozen = verify(); baseline = json.loads((ROOT / 'verification/BASELINE.json').read_text(encoding='utf-8'))
    assert sha(ROOT / 'ss_multicode/algebra.py') == baseline['copied_algebra_sha256']
    vendor = ROOT / 'vendor/PLM-L1-SS-online-v0.1.zip'; assert sha(vendor) == baseline['vendor_sha256']
    with zipfile.ZipFile(vendor) as z:
        assert z.testzip() is None; prefix = 'PLM-L1-SS-online-v0.1/'
        manifest = json.loads(z.read(prefix + 'RELEASE_MANIFEST.json'))['files']
        assert all(hashlib.sha256(z.read(prefix + n)).hexdigest() == h for n, h in manifest.items())
    stdout, stderr = command(['-m', 'unittest', 'discover', '-s', 'tests', '-v'], ROOT, out / 'UNIT_TESTS.log')
    tests = int(re.search(r'Ran (\d+) tests', stdout + stderr).group(1))
    calibration_digest, grid_count = verify_calibration()
    result = json.loads((ROOT / 'results/EVALUATION.json').read_text(encoding='utf-8')); claimed = result.pop('result_digest')
    assert digest(result) == claimed and result['freeze_hash'] == frozen and result['calibration_digest'] == calibration_digest
    assert result['all_checks_passed'] and len(result['runs']) == 104
    cases = {c['seed']: c for c in json.loads((ROOT / 'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
    with np.load(ROOT / 'results/SCORES.npz', allow_pickle=False) as z:
        assert set(z.files) == set(result['arrays'])
        arrays = {k: z[k] for k in z.files}
    for k, values in arrays.items():
        meta = result['arrays'][k]
        assert list(values.shape) == meta['shape'] and hashlib.sha256(values.astype('<f8').tobytes()).hexdigest() == meta['sha256']
    snapshots = 0
    for run in result['runs']:
        case = cases[run['data_seed']]; events = events_for(case, run['scenario'])
        assert len(events) == run['teacher_presentations'] == 896
        assert digest([(e['id'], e['teacher_label']) for e in events]) == run['teacher_sequence_digest']
        anchors = {}
        for snap in run['snapshots']:
            known = {e['id'] for e in events[:snap['step']]}
            raw = {k: arrays[snap['prefix'] + '_' + k] for k in ('readers', 'checker')}
            assert snapshot_summary(raw, run['policies'], case, known, snap['phase'], snap['epoch'], anchors) == snap['metrics']
            snapshots += 1
        raw = {stage: {k: arrays[run['trace_prefix'] + '_' + stage + '_' + k] for k in ('readers', 'checker')} for stage in ('before', 'after')}
        assert trace_summary(raw['before'], raw['after'], events, run['policies']) == run['blocks']
    # Copy-only clone control: identical individual-bank scores on every probe and presentation.
    clone_checks = 0
    for run in [r for r in result['runs'] if r['architecture'] == 'clone4']:
        ref = next(r for r in result['runs'] if r['architecture'] == 'single128' and all(r[k] == run[k] for k in ('data_seed', 'scenario', 'seed')))
        for a, b in zip(run['snapshots'], ref['snapshots']):
            ra = arrays[a['prefix'] + '_readers']; rb = arrays[b['prefix'] + '_readers']
            for i in range(4): np.testing.assert_array_equal(ra[:, i], rb[:, 0])
            clone_checks += 1
    models = {}; presentations = 0
    with tempfile.TemporaryDirectory(prefix='mcverify-') as temp:
        base = Path(temp).resolve(); trainer = base / 'trainer'; runtime = base / 'runtime'
        trainer.mkdir(); runtime.mkdir()
        shutil.copytree(ROOT / 'ss_multicode', trainer / 'ss_multicode', ignore=shutil.ignore_patterns('__pycache__'))
        (runtime / 'ss_multicode').mkdir()
        for name in ('__init__.py', 'algebra.py', 'model.py', '__main__.py'):
            shutil.copyfile(ROOT / 'ss_multicode' / name, runtime / 'ss_multicode' / name)
        for run in [r for r in result['runs'] if r['saved']]:
            case = cases[run['data_seed']]; events = events_for(case, run['scenario'])
            desc = {'architecture': run['architecture'], 'seed': run['seed'], 'acceptance': run['policies']['calibrated'],
                    'teaching': [{'context': e['context'], 'label': e['teacher_label']} for e in events],
                    'checkpoints': {str(v['step']): name for name, v in run['saved'].items()}}
            write(trainer / 'input.json', desc)
            code = "import json,numpy as np;from ss_multicode.model import Model;from ss_multicode.learning import Learner,teacher;d=json.load(open('input.json',encoding='utf-8'));s=Learner(Model(d['architecture'],d['seed'],acceptance=d['acceptance']));a={k:[] for k in ('before_readers','before_checker','after_readers','after_checker')}\nfor e in d['teaching']:\n r=s.model.raw([e['context']]);[a['before_'+k].append(v[0]) for k,v in r.items()];q=s.question(e['context'])['request'];s=s.answer(q,teacher(q,e['label']));r=s.model.raw([e['context']]);[a['after_'+k].append(v[0]) for k,v in r.items()]\n if str(s.step) in d['checkpoints']:s.save(d['checkpoints'][str(s.step)])\nnp.savez('trace.npz',**{k:np.array(v) for k,v in a.items()});print(s.fingerprint)"
            command(['-c', code], trainer, out / (run['architecture'] + '-TRAIN.log'))
            with np.load(trainer / 'trace.npz', allow_pickle=False) as z:
                for key in z.files: np.testing.assert_array_equal(z[key], arrays[run['trace_prefix'] + '_' + key])
            (trainer / 'input.json').unlink(); (trainer / 'trace.npz').unlink(); presentations += len(events)
            contexts = [r['context'] for g in ('A', 'B', 'C') for r in case['groups'][g]] + case['unknown']
            for name, meta in run['saved'].items():
                original = Learner.load(ROOT / 'results' / name); fresh = Learner.load(trainer / name)
                assert original.fingerprint == fresh.fingerprint == meta['fingerprint']
                np.testing.assert_array_equal(original.model.readers, fresh.model.readers)
                np.testing.assert_array_equal(original.model.checker, fresh.model.checker)
                assert original.model.entries == fresh.model.entries
                shutil.copytree(ROOT / 'results' / name / 'model', runtime / name); write(runtime / 'queries.json', contexts)
                stdout, _ = command(['-m', 'ss_multicode', 'query', '--model', name, '--input', 'queries.json'], runtime, out / (name + '-QUERY.log'), (0, 2))
                assert json.loads(stdout) == original.model.predict(contexts)
                (runtime / 'queries.json').unlink()
                models[name] = {'contexts': len(contexts), 'coefficient_max_difference': 0, 'strict_fingerprint_equal': True}
        command(['-c', "from pathlib import Path;import sys;from ss_multicode.model import Model;assert not Path('ss_multicode/learning.py').exists();assert not Path('data').exists();assert not Path('evaluation').exists();assert not list(Path('.').rglob('learner.json'));assert not any(n.startswith('ss_multicode.learning') for n in sys.modules);print('Predictor contains no learner, teacher sequence, evaluation truth or replay')"], runtime, out / 'BOUNDARY.log')
        selected = next(r for r in result['runs'] if 'checked-A' in r['saved'])
        event = events_for(cases[selected['data_seed']], 'clean')[256]
        learner = Learner.load(ROOT / 'results/checked-A'); req = learner.question(event['context'])['request']; fb = teacher(req, event['teacher_label']); expected = learner.answer(req, fb)
        write(trainer / 'request.json', req); write(trainer / 'feedback.json', fb)
        command(['-m', 'ss_multicode', 'teach', '--learner', 'checked-A', '--request', 'request.json', '--feedback', 'feedback.json', '--out', 'resumed'], trainer, out / 'RESUME.log')
        assert Learner.load(trainer / 'resumed').fingerprint == expected.fingerprint
        command(['-m', 'ss_multicode', 'teach', '--learner', 'resumed', '--request', 'request.json', '--feedback', 'feedback.json', '--out', 'stale-output'], trainer, out / 'STALE.log', (2,))
        assert not (trainer / 'stale-output').exists()
        (trainer / 'feedback.json').unlink(); write(trainer / 'feedback.json', dict(fb, source='model_prediction'))
        command(['-m', 'ss_multicode', 'teach', '--learner', 'checked-A', '--request', 'request.json', '--feedback', 'feedback.json', '--out', 'pseudo-output'], trainer, out / 'PSEUDO.log', (2,))
        assert not (trainer / 'pseudo-output').exists()
    manifest_count = None
    if (ROOT / 'RELEASE_MANIFEST.json').exists():
        manifest = json.loads((ROOT / 'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files']
        actual = {p.relative_to(ROOT).as_posix(): sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'RELEASE_MANIFEST.json'}
        assert actual == manifest; manifest_count = len(actual)
    report = {'status': 'passed', 'unit_tests': tests, 'freeze_hash': frozen, 'result_digest': claimed,
              'calibration_grid_rows_rechecked': grid_count, 'raw_arrays_rechecked': len(arrays), 'probe_snapshots_rechecked': snapshots,
              'clone_probe_checks': clone_checks, 'isolated_sequential_presentations': presentations, 'models': models,
              'prediction_without_teacher_or_replay': True, 'cli_resume_matches': True,
              'stale_and_pseudo_feedback_rejected_without_output': True, 'manifest_files': manifest_count,
              'all104_trajectories_retrained_here': False, 'linux_tested': False, 'p1_s1_integrated': False, 'eligible_for_inference': False}
    write(out / 'VERIFICATION.json', report); print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__': main()
