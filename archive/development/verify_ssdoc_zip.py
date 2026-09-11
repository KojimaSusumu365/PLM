"""Post-ZIP tests and known-time-relation isolated generation; not another full replay."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
package = json.loads((WORK / 'ssdoc-package.json').read_text(encoding='utf-8'))
ROOT = Path(package['extracted_root'])
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, sha, verify
from verify_release import copy_generator


def check_manifest():
    actual = {p.relative_to(ROOT).as_posix(): sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name != 'RELEASE_MANIFEST.json'}
    assert actual == read(ROOT / 'RELEASE_MANIFEST.json')['files']
    return len(actual)


def main():
    verify()
    filecount = check_manifest()
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    environment['OPENBLAS_NUM_THREADS'] = '1'
    environment['PYTHONIOENCODING'] = 'utf-8'
    command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v']
    proc = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0 and 'Ran 26 tests' in proc.stderr, proc.stderr
    test_result = {'command': command, 'cwd': str(ROOT), 'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
    groot = WORK / 'ssdoc-zip-generator'
    groot.mkdir(exist_ok=False)
    copy_generator(groot)
    shutil.copytree(ROOT / 'results/models/s0-c0', groot / 'model')
    shutil.copy2(WORK / 'ssdoc_isolated_cli.py', groot / 'run.py')
    for path in groot.rglob('*.py'):
        assert path.name not in ('reader.py', 'training.py')
    assert not (groot / 'data').exists() and not (groot / 'evaluation').exists()
    examples = read(ROOT / 'examples/EXAMPLES.json')
    for ex in examples:
        shutil.copy2(ROOT / 'examples' / ex['packet'], groot / ex['packet'])
    before = {p.relative_to(groot).as_posix(): sha(p) for p in groot.rglob('*') if p.is_file()}
    generated = []
    for ex in examples:
        packet = read(groot / ex['packet'])
        assert set(packet) == {'schema', 'model_fingerprint', 'dimension', 'real', 'imag', 'eligible_for_inference'}
        command = [sys.executable, '-I', '-B', '-X', 'utf8', 'run.py', 'generate', '--model', 'model', '--packet', ex['packet'], '--order', 'reverse']
        proc = subprocess.run(command, cwd=groot, env=environment, capture_output=True, text=True, encoding='utf-8')
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result['status'] == 'generated' and result['text'] == ex['output']
        provenance = json.loads(proc.stderr)
        assert provenance['paths_within_generator_directory']
        generated.append({'packet': ex['packet'], 'command': command, 'result': result,
                          'import_provenance': provenance, 'exact_text_equal': True,
                          'expected_text_supplied_only_to_parent_verifier': True,
                          'event_count_or_goals_not_supplied': True})
    after = {p.relative_to(groot).as_posix(): sha(p) for p in groot.rglob('*') if p.is_file()}
    assert before == after
    assert check_manifest() == filecount
    assert sha(Path(package['archive'])) == package['sha256']
    report = {'passed': True, 'package': package, 'manifest_files_checked': filecount,
              'tests': test_result, 'isolated_known_relation_examples': generated,
              'isolated_directory_files_sha256': before,
              'full_numeric_replay_repeated_after_zip': False,
              'scope': 'Full replay passed before ZIP; all ZIP files byte-identical. After extraction: 26 tests and 3 isolated known-time-relation examples.',
              'eligible_for_inference': False}
    write(WORK / 'ssdoc-zip-verify.json', report)
    print(json.dumps({'passed': True, 'tests': 26, 'isolated_examples': len(generated), 'manifest_files_checked': filecount}))


if __name__ == '__main__':
    main()
