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
from plm_l1_v011.algebra import digest
from plm_l1_v012.core import GuardedModel
from plm_l1_v012.portability import compare
from evaluation.integrity import ROOT, manifest, sha, verify_freeze
from evaluation.cases import query_stages
from evaluate import judge, write

V011_SHA = '73c87a79af05acbbd9cc04400c36afdbbe5594534d31e4dc83baf72fd0193c21'


def run(args, cwd, out, name, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    p = subprocess.run([sys.executable, '-B', *args], cwd=cwd, env=env, capture_output=True, text=True, encoding='utf-8', timeout=300)
    (out / (name + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
    if p.returncode != expected:
        raise ValueError(name + ': ' + (p.stdout + p.stderr)[-5000:])
    return p.stdout, p.stderr


def copy_runtime(destination, inference_only=False):
    for package in ('plm_l1_v011', 'plm_l1_v012'):
        for source in (ROOT / package).glob('*.py'):
            if inference_only and source.name == 'training.py':
                continue
            target = destination / package / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def vendor_checks():
    archive = ROOT / 'vendor/PLM-L1-v0.11.zip'
    if sha(archive) != V011_SHA:
        raise ValueError('v011_archive_changed')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('vendor_crc_error')
        prefix = 'PLM-L1-v0.11/'
        wanted = json.loads(z.read(prefix + 'RELEASE_MANIFEST.json'))['files']
        actual = {i.filename[len(prefix):]: hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir() and i.filename != prefix + 'RELEASE_MANIFEST.json'}
        if wanted != actual:
            raise ValueError('vendor_manifest_mismatch')
        for p in (ROOT / 'plm_l1_v011').glob('*.py'):
            if hashlib.sha256(z.read(prefix + 'plm_l1_v011/' + p.name)).hexdigest() != sha(p):
                raise ValueError('copied_legacy_runtime_modified')
    return {'v011_sha256': V011_SHA, 'manifest_files': len(actual), 'legacy_runtime_unchanged': True, 'crc_verified': True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--mode', choices=('strict', 'functional'), default='strict')
    a = p.parse_args()
    out = Path(a.out).resolve()
    if out.is_relative_to(ROOT):
        raise ValueError('verification_output_must_be_outside_release')
    out.mkdir(parents=True, exist_ok=False)
    frozen = verify_freeze()
    result = json.loads((ROOT / 'results/EVALUATION.json').read_text(encoding='utf-8'))
    claimed = result.pop('result_digest')
    if digest(result) != claimed or result['freeze_hash'] != frozen or judge(result) != result['checks'] or not result['all_checks_passed']:
        raise ValueError('evaluation_integrity_failure')
    stdout, stderr = run(['-m', 'unittest', 'discover', '-s', 'tests', '-v'], ROOT, out, 'UNIT_TESTS')
    tests = int(re.search(r'Ran (\d+) tests', stdout + stderr).group(1))
    vendor = vendor_checks()
    tasks = {t['id']: t for t in json.loads((ROOT / 'data/v011-regression.json').read_text(encoding='utf-8'))}
    trainer = out / 'train-only'
    copy_runtime(trainer)
    run(['-c', "import importlib.util; from pathlib import Path; assert importlib.util.find_spec('evaluation') is None; assert not any(Path(x).exists() for x in ('data','results','vendor')); print('No evaluator, truth table, vendor or old weights')"], trainer, out, 'TRAIN_BOUNDARY')
    comparisons = {}
    for name, record in result['saved_models'].items():
        task = tasks[record['task_id']]
        source = GuardedModel.load(ROOT / 'results' / name)
        if source.fingerprint != record['fingerprint']:
            raise ValueError('saved_model_result_mismatch')
        for field, rows in (('train', task['train'] + (task['added'] if record['after'] else [])), ('selection', task['selection']), ('calibration', task['calibration'])):
            write(trainer / (name + '-' + field + '.json'), rows)
        run(['-m', 'plm_l1_v012', 'train', '--train', name + '-train.json', '--selection', name + '-selection.json', '--calibration', name + '-calibration.json', '--out', name,
             '--representation', source.base.config['representation'], '--selector', source.base.config['selector'], '--dimension', str(source.base.config['requested_dimension']), '--seed', source.base.config['seed']], trainer, out, 'TRAIN_' + name)
        refit = GuardedModel.load(trainer / name)
        contexts = [q['context'] for _, queries in query_stages(task, True) for q in queries]
        check = compare(source, refit, contexts)
        if not check['functional_passed'] or (a.mode == 'strict' and not check['strict_fingerprint_equal']):
            raise ValueError('isolated_refit_mismatch')
        comparisons[name] = check
    runtime = out / 'query-only'
    copy_runtime(runtime, inference_only=True)
    shutil.copytree(ROOT / 'results/and2', runtime / 'model')
    run(['-c', "import importlib.util; from pathlib import Path; assert all(importlib.util.find_spec(x) is None for x in ('evaluation','plm_l1_v011.training','plm_l1_v012.training')); assert not Path('data').exists(); print('Learned-memory queries without trainers, teachers or oracle')"], runtime, out, 'QUERY_BOUNDARY')
    model = GuardedModel.load(runtime / 'model')
    task = tasks[result['saved_models']['and2']['task_id']]
    partial = dict(query_stages(task))['semantic_missing']
    sufficient = next(q for q in partial if len(q['allowed']) == 1 and model.predict(q['context'])['value'] is not None)
    ambiguous = next(q for q in partial if len(q['allowed']) > 1 and model.predict(q['context'], policy='baseline')['value'] is not None)
    demos = []
    for label, query in (('sufficient', sufficient['context']), ('ambiguous', ambiguous['context']), ('empty', {})):
        write(runtime / (label + '.json'), query)
        expected = model.predict(query)
        stdout, _ = run(['-m', 'plm_l1_v012', 'query', '--model', 'model', '--input', label + '.json'], runtime, out, 'QUERY_' + label, 0 if expected['value'] is not None else 2)
        actual = json.loads(stdout)
        if actual != expected:
            raise ValueError('isolated_guard_query_mismatch')
        demos.append({'name': label, 'context': query, 'status': actual['status'], 'value': actual['value']})
    write(runtime / 'bad.json', {'oracle': 'must-not-be-used'})
    run(['-m', 'plm_l1_v012', 'query', '--model', 'model', '--input', 'bad.json'], runtime, out, 'INVALID_QUERY', 2)
    count = manifest() if (ROOT / 'RELEASE_MANIFEST.json').exists() else 'not_yet_packaged'
    report = {'status': 'passed', 'mode': a.mode, 'unit_tests': tests, 'source_freeze': frozen, 'result_digest': claimed,
              'comparisons': comparisons, 'isolated_training_without_evaluator': True, 'guard_queries_without_trainers_or_oracle': True,
              'query_demos': demos, 'vendor': vendor, 'manifest_files': count, 'linux_execution_performed': False,
              'numeric_only_guard_implemented': False, 'p1_s1_integration_performed': False,
              'full_numeric_evaluation_rerun_by_this_command': False}
    write(out / 'VERIFICATION.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
