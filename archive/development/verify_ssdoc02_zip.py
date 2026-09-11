"""Run extracted tests and verifier; record post-ZIP evidence outside sealed files."""
import json
import os
import subprocess
import sys
from pathlib import Path
WORK = Path(__file__).resolve().parent
package = json.loads((WORK / 'ssdoc02-package.json').read_text(encoding='utf-8'))
ROOT = Path(package['extracted_root'])
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, sha


def main():
    environment = dict(os.environ); environment['OPENBLAS_NUM_THREADS'] = '1'; environment['PYTHONIOENCODING'] = 'utf-8'
    environment.pop('PYTHONPATH', None)
    cmd = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v']
    tests = subprocess.run(cmd, cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8')
    assert tests.returncode == 0 and 'Ran 41 tests' in tests.stderr, tests.stderr
    target = WORK / 'ssdoc02-zip-verifier'
    cmd = [sys.executable, '-B', 'verify_release.py', '--out', str(target), '--repeat', str(WORK / 'ssdoc02-repeat')]
    check = subprocess.run(cmd, cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8')
    assert check.returncode == 0, check.stderr
    result = read(target / 'VERIFY.json'); assert result['passed']
    assert result['manifest_files_checked'] == package['manifest_files']
    assert sha(Path(package['archive'])) == package['archive_sha256']
    write(WORK.parent / 'outputs/PLM-L1-SS-doc-v0.2-POSTZIP.json', {
        'passed': True, 'package': package, 'tests': {'returncode': tests.returncode, 'stdout': tests.stdout, 'stderr': tests.stderr},
        'extracted_verifier': result, 'isolated': read(target / 'ISOLATED.json'),
        'scope': 'All extracted bytes equal. 41 tests; 144 reference arrays recalculated; two isolated updates and generations; full second-run result files compared. Not a third full evaluation.',
        'eligible_for_inference': False})
    print(json.dumps({'passed': True, 'tests': 41, 'extracted_verifier': result}, indent=2), flush=True)


if __name__ == '__main__': main()
