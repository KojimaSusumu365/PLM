import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from plm_l1_v013.algebra import digest
from plm_l1_v013.core import Model
from plm_l1_v013.teaching import Session
from plm_l1_v013.portability import compare
from evaluation.integrity import ROOT, sha, manifest, verify_freeze
from evaluation.cases import queries
from evaluate import write, judge
V012_SHA = 'ac77bd1073110b270d17b5b55939fc7bf079cd0f1b5c8202e1b6cfb2137cc68a'


def run(args, cwd, out, name, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    p = subprocess.run([sys.executable, '-B', *args], cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', timeout=300)
    (out / (name + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
    if p.returncode != expected:
        raise ValueError(name + ': ' + (p.stdout + p.stderr)[-5000:])
    return p.stdout, p.stderr


def copy_runtime(target, query_only=False):
    for p in (ROOT / 'plm_l1_v013').glob('*.py'):
        if query_only and p.name in ('training.py', 'teaching.py'):
            continue
        dest = target / 'plm_l1_v013' / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)


def vendor_check():
    archive = ROOT / 'vendor/PLM-L1-v0.12.zip'
    if sha(archive) != V012_SHA:
        raise ValueError('v012_archive_changed')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('vendor_crc_error')
        prefix = 'PLM-L1-v0.12/'
        expected = json.loads(z.read(prefix + 'RELEASE_MANIFEST.json'))['files']
        actual = {i.filename[len(prefix):]: hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir() and i.filename != prefix + 'RELEASE_MANIFEST.json'}
        if actual != expected:
            raise ValueError('vendor_manifest_mismatch')
        if hashlib.sha256(z.read(prefix + 'plm_l1_v011/algebra.py')).hexdigest() != sha(ROOT / 'plm_l1_v013/algebra.py'):
            raise ValueError('shared_phase_algebra_changed')
    return {'v012_sha256': V012_SHA, 'crc_verified': True, 'manifest_files': len(expected), 'phase_algebra_unchanged': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--mode', choices=('strict', 'functional'), default='strict')
    a = parser.parse_args()
    out = Path(a.out).resolve()
    if out.is_relative_to(ROOT):
        raise ValueError('verification_output_must_be_outside_release')
    out.mkdir(parents=True, exist_ok=False)
    freeze = verify_freeze()
    result = json.loads((ROOT / 'results/EVALUATION.json').read_text(encoding='utf-8'))
    claimed = result.pop('result_digest')
    if digest(result) != claimed or result['freeze_hash'] != freeze or judge(result) != result['checks'] or not result['all_checks_passed']:
        raise ValueError('evaluation_integrity_failure')
    stdout, stderr = run(['-m', 'unittest', 'discover', '-s', 'tests', '-v'], ROOT, out, 'UNIT_TESTS')
    unit_tests = int(re.search(r'Ran (\d+) tests', stdout + stderr).group(1))
    vendor = vendor_check()
    tasks = {t['id']: t for t in json.loads((ROOT / 'data/evaluation.json').read_text(encoding='utf-8'))}
    trainer = out / 'train-only'
    copy_runtime(trainer)
    run(['-c', "import importlib.util; from pathlib import Path; assert importlib.util.find_spec('evaluation') is None; assert not any(Path(x).exists() for x in ('vendor','data','results')); print('No evaluator, pool answers, test truth, vendor or old weights')"], trainer, out, 'TRAIN_BOUNDARY')
    comparisons = {}
    for name, record in result['saved_sessions'].items():
        source_session = Session.load(ROOT / 'results' / name)
        source = source_session.model
        if source.fingerprint != record['fingerprint']:
            raise ValueError('saved_model_result_mismatch')
        write(trainer / (name + '-train.json'), source_session.rows)
        s = record['settings']
        run(['-m', 'plm_l1_v013', 'train', '--train', name + '-train.json', '--out', name, '--backend', s['backend'], '--dimension', str(s['dimension']), '--seed', s['seed'], '--retention', s['retention']], trainer, out, 'TRAIN_' + name)
        refit = Model.load(trainer / name)
        contexts = [q['context'] for _, qs in queries(tasks[record['task_id']]) for q in qs]
        check = compare(source, refit, contexts, source_session.pool)
        if not check['functional_passed'] or (a.mode == 'strict' and not check['strict_fingerprint_equal']):
            raise ValueError('isolated_refit_mismatch')
        comparisons[name] = check
    runtime = out / 'runtime-only'
    copy_runtime(runtime, query_only=True)
    before = Session.load(ROOT / 'results/hidden-b0')
    after = Session.load(ROOT / 'results/hidden-b16')
    shutil.copytree(ROOT / 'results/hidden-b0/model', runtime / 'before')
    shutil.copytree(ROOT / 'results/hidden-b16/model', runtime / 'after')
    write(runtime / 'pool.json', before.pool)
    run(['-c', "import importlib.util; from pathlib import Path; assert all(importlib.util.find_spec(x) is None for x in ('evaluation','plm_l1_v013.training','plm_l1_v013.teaching')); assert not Path('session.json').exists(); print('Prediction and selection without teachers, sessions or evaluator')"], runtime, out, 'RUNTIME_BOUNDARY')
    request = before.choose()
    stdout, _ = run(['-m', 'plm_l1_v013', 'select', '--model', 'before', '--pool', 'pool.json'], runtime, out, 'SELECT')
    if json.loads(stdout) != request:
        raise ValueError('isolated_selection_mismatch')
    task = tasks[result['saved_sessions']['hidden-b0']['task_id']]
    candidates = [r['context'] for r in task['test']]
    first = before.model.predict_many(candidates)
    last = after.model.predict_many(candidates)
    chosen = next(c for c, p, q in zip(candidates, first, last) if p['value'] is None and q['value'] is not None)
    write(runtime / 'query.json', chosen)
    demos = []
    for label, model in (('before', before.model), ('after', after.model)):
        expected = model.predict(chosen)
        stdout, _ = run(['-m', 'plm_l1_v013', 'query', '--model', label, '--input', 'query.json'], runtime, out, 'QUERY_' + label, 0 if expected['value'] is not None else 2)
        if json.loads(stdout) != expected:
            raise ValueError('isolated_query_mismatch')
        demos.append({'stage': label, 'context': chosen, 'value': expected['value'], 'reason': expected['reason']})
    # Resume/teach is checked separately from the predictor-only boundary.
    shutil.copytree(ROOT / 'results/hidden-b0', trainer / 'session')
    write(trainer / 'request.json', request)
    teacher_label = task['teacher_answers'][request['id']]
    run(['-m', 'plm_l1_v013', 'teach', '--session', 'session', '--request', 'request.json', '--label', teacher_label, '--out', 'updated'], trainer, out, 'TEACH_ONE')
    updated = Session.load(trainer / 'updated')
    if updated.model.fingerprint != result['saved_sessions']['hidden-b1']['fingerprint']:
        raise ValueError('isolated_teaching_mismatch')
    run(['-m', 'plm_l1_v013', 'teach', '--session', 'updated', '--request', 'request.json', '--label', teacher_label, '--out', 'must-not-exist'], trainer, out, 'STALE_REQUEST', 2)
    if (trainer / 'must-not-exist').exists():
        raise ValueError('stale_request_wrote_output')
    count = manifest() if (ROOT / 'RELEASE_MANIFEST.json').exists() else 'not_yet_packaged'
    report = {'status': 'passed', 'mode': a.mode, 'unit_tests': unit_tests, 'source_freeze': freeze, 'result_digest': claimed,
              'comparisons': comparisons, 'isolated_training_without_evaluator': True,
              'prediction_and_selection_without_teachers': True, 'one_teacher_resume_matches': True,
              'stale_teacher_rejected_without_output': True, 'demos': demos, 'vendor': vendor, 'manifest_files': count,
              'linux_execution_performed': False, 'numeric_only_semantic_guard': False, 'p1_s1_integration_performed': False,
              'full_evaluation_rerun_by_this_command': False}
    write(out / 'VERIFICATION.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
