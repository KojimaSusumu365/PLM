"""Seal the online-learning release; extract and verify the actual archive."""
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

workspace = Path(__file__).resolve().parents[1]
name = 'PLM-L1-SS-online-v0.1'
root = workspace / 'outputs' / name
sys.path.insert(0, str(root))
from evaluation.integrity import sha, verify, write

frozen = verify()
for file in ('REPORT.md', 'verification/isolation/VERIFICATION.json',
             'verification/SUMMARY.json', 'verification/BENCHMARK.json',
             'verification/REPEATABILITY.json', 'verification/PRESERVATION.json'):
    assert (root / file).is_file(), file
assert json.loads((root / 'verification/isolation/VERIFICATION.json').read_text(encoding='utf-8'))['status'] == 'passed'
repeat = json.loads((root / 'verification/REPEATABILITY.json').read_text(encoding='utf-8'))
assert repeat['all_equal'] and len(repeat['files']) == 29
assert json.loads((root / 'verification/PRESERVATION.json').read_text(encoding='utf-8'))['all_unchanged']
# Recheck original files now, not only the saved preservation assertion.
baseline = json.loads((root / 'verification/BASELINE.json').read_text(encoding='utf-8'))
assert all(sha(root.parent / n) == h for n, h in baseline['previous_files'].items())
result = json.loads((root / 'results/EVALUATION.json').read_text(encoding='utf-8'))
files = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
         if p.is_file() and '__pycache__' not in p.parts and p.name != 'RELEASE_MANIFEST.json'}
archive = root.parent / (name + '.zip')
assert not archive.exists() and not (root / 'RELEASE_MANIFEST.json').exists()
write(root / 'RELEASE_MANIFEST.json', {
    'files': files, 'freeze_hash': frozen, 'result_digest': result['result_digest']})
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            z.write(p, name + '/' + p.relative_to(root).as_posix(),
                    compress_type=zipfile.ZIP_STORED if p.suffix in ('.zip', '.npz') else zipfile.ZIP_DEFLATED)
record = {'archive': archive.name, 'sha256': sha(archive), 'bytes': archive.stat().st_size,
          'files': len(files) + 1, 'freeze_hash': frozen, 'result_digest': result['result_digest']}
write(root.parent / (name + '-ARCHIVE.json'), record)
print(json.dumps(record), flush=True)
with tempfile.TemporaryDirectory(prefix='sozip-') as folder:
    base = Path(folder).resolve()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        seen = set()
        for item in z.infolist():
            dest = (base / item.filename).resolve()
            assert dest.is_relative_to(base) and item.filename.startswith(name + '/')
            assert len(str(dest)) < 250 and str(dest).casefold() not in seen
            seen.add(str(dest).casefold())
        assert len(seen) == record['files']
        z.extractall(base)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8',
               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    log_path = root.parent / (name + '-ARCHIVE-VERIFICATION.log')
    with log_path.open('x', encoding='utf-8') as log:
        process = subprocess.run(
            [sys.executable, '-B', 'verify_release.py', '--out', str(base / 'verified')],
            cwd=base / name, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
    assert process.returncode == 0, log_path.read_text(encoding='utf-8')[-2500:]
    verified = json.loads((base / 'verified/VERIFICATION.json').read_text(encoding='utf-8'))
    assert verified['status'] == 'passed' and verified['manifest_files'] == len(files)
    verified.update({'archive': record, 'archive_actually_extracted': True, 'crc_verified': True,
                     'full_evaluations_before_packaging': 2, 'repeat_equal_files': 29,
                     'preserved_previous_files': len(baseline['previous_files'])})
    write(root.parent / (name + '-VERIFICATION.json'), verified)
    print(json.dumps({'archive_verification': verified['status'], 'unit_tests': verified['unit_tests'],
                      'manifest_files': verified['manifest_files']}), flush=True)
