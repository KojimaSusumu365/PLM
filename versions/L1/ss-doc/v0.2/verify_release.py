"""Check full rerun bytes, reference vectors, and reader-free update/generation."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT, read, write, sha, verify
from evaluation.cases import cases, scenes
from evaluation.experiment import trial
from evaluation.oracle import localize, scored
from ss_partial.runtime import PartialModel
from ss_partial.update import request


def copy_runtime(target, updater=False):
    specs = {
        'ss_partial': ['__init__.py', 'contract.py', 'codec.py', 'runtime.py', '__main__.py'],
        'ss_document': ['__init__.py', 'contract.py', 'codec.py', 'runtime.py'],
        'plm_l1_v09': ['__init__.py', 'contract.py', 'codec.py', 'runtime.py', 'thresholds.py'],
        'plm_l1_v09/component': ['__init__.py', 'runtime.py', 'algebra.py', 'lexicon.py', 'features.py', 'banked.py', 'projection.py']}
    if updater: specs['ss_partial'].append('update.py')
    for package, names in specs.items():
        folder = target / package; folder.mkdir(parents=True, exist_ok=True)
        for name in names: shutil.copy2(ROOT / package / name, folder / name)
    shutil.copy2(ROOT / 'verification/isolated_cli.py', target / 'run.py')


def manifest_check():
    if not (ROOT / 'RELEASE_MANIFEST.json').exists(): return None
    actual = {p.relative_to(ROOT).as_posix(): sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name != 'RELEASE_MANIFEST.json'}
    assert actual == read(ROOT / 'RELEASE_MANIFEST.json')['files']
    return len(actual)


def run(out, repeat=None):
    freeze = verify(); out = Path(out); out.mkdir(parents=True, exist_ok=False)
    result = read(ROOT / 'results/EVALUATION.json')
    corpus = read(ROOT / 'results/CASES.json'); assert corpus == cases('evaluation')
    assert read(ROOT / 'results/SCENES.json') == scenes('evaluation')
    models = {}
    for spec in result['models']:
        model = PartialModel.load(ROOT / 'results/models' / spec['id'])
        assert model.fingerprint == spec['fingerprint']; models[spec['id']] = model
    equal_files = None
    if repeat is not None:
        def hashes(root):
            return {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file() and p.name != 'PERFORMANCE.json'}
        original = hashes(ROOT / 'results'); second = hashes(Path(repeat))
        assert original == second, 'full_rerun_differs'
        write(out / 'REPEATABILITY.json', {'passed': True, 'files': original, 'file_count': len(original), 'excluded': ['PERFORMANCE.json']})
        equal_files = len(original)
    arrays_checked = 0
    with np.load(ROOT / 'results/REFERENCE_SIGNALS.npz', allow_pickle=False) as stored:
        expected_keys = set()
        for seed in range(3):
            mid = f's{seed}-8192-bound'; model = models[mid]
            for count in (2, 3):
                selected = [(i, c) for i, c in enumerate(corpus) if c['observation']['count'] == count][:12]
                for index, case in selected:
                    actual, arrays = trial(model, case)
                    expected = result['primary'][seed * len(corpus) + index]
                    assert actual == {k: v for k, v in expected.items() if k != 'model_id'}
                    for key, vector in arrays.items():
                        name = f'{mid}-{index}-{key}'; expected_keys.add(name)
                        np.testing.assert_array_equal(vector, stored[name]); arrays_checked += 1
        assert expected_keys == set(stored.files)
    model = models['s0-8192-bound']
    uroot, groot = out / 'updater', out / 'generator'
    for folder, include_update in ((uroot, True), (groot, False)):
        folder.mkdir(); copy_runtime(folder, include_update)
        shutil.copytree(ROOT / 'results/models/s0-8192-bound', folder / 'model')
    environment = dict(os.environ); environment.pop('PYTHONPATH', None)
    environment['OPENBLAS_NUM_THREADS'] = '1'
    def command(folder, args):
        cmd = [sys.executable, '-I', '-B', '-X', 'utf8', 'run.py', *args]
        p = subprocess.run(cmd, cwd=folder, env=environment, capture_output=True, text=True, encoding='utf-8')
        assert p.returncode == 0, p.stderr
        return {'command': cmd, 'result': __import__('json').loads(p.stdout), 'provenance': __import__('json').loads(p.stderr)}
    isolated = []
    for n in (2, 3):
        case = next(c for c in corpus if c['observation']['count'] == n and c['scene_id'].endswith('/1') and c['target'] == 'event:1/subject' and c['observation']['cells'][c['target']]['state'] == 'ambiguous')
        packet = model.encode(case['observation'])
        write(uroot / f'input{n}.json', packet)
        write(uroot / f'teacher{n}.json', request(packet, case['target'], case['teacher_value']))
        updated = command(uroot, ['update', '--model', 'model', '--packet', f'input{n}.json', '--message', f'teacher{n}.json', '--out', f'corrected{n}.json'])
        assert updated['result']['status'] == 'updated'
        shutil.copy2(uroot / f'corrected{n}.json', groot / f'packet{n}.json')
        generated = command(groot, ['generate', '--model', 'model', '--packet', f'packet{n}.json', '--order', 'reverse'])
        assert generated['result']['status'] == 'generated'
        expected = localize(case['expected_meaning'], list(reversed(case['expected_meaning']['presentation'])), ['subject'] * n)
        score = scored(expected, generated['result']['text']); assert score['semantic_equal'] and score['goals_equal']
        assert not any('update' in name for name in generated['provenance']['local_modules'])
        isolated.append({'count': n, 'case_id': case['id'], 'update': updated, 'generation': generated, 'independent_score': score,
                         'teacher_present_only_in_updater': True, 'generator_without_reader_updater_teacher_or_evaluator': True,
                         'no_goals_or_count_argument': True})
    write(out / 'ISOLATED.json', isolated)
    summary = {'passed': True, 'frozen_source_digest': freeze, 'models_loaded': len(models), 'reference_arrays_recomputed': arrays_checked,
               'full_rerun_equal_files': equal_files, 'isolated_updates': len(isolated), 'isolated_generations': len(isolated),
               'manifest_files_checked': manifest_check(), 'eligible_for_inference': False}
    write(out / 'VERIFY.json', summary); print(__import__('json').dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); p.add_argument('--repeat'); a = p.parse_args(); run(a.out, a.repeat)
