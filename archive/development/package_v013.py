"""Package the verified v0.13 tree without overwriting an existing release."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'outputs/PLM-L1-v0.13'
sys.path.insert(0, str(root))
from evaluation.integrity import sha, verify_freeze

required = ('REPORT.md', 'verification/strict/VERIFICATION.json',
            'verification/v012/VERIFICATION.json', 'verification/REPEATABILITY.json',
            'verification/PRESERVATION_CHECK.json', 'verification/BENCHMARK.json',
            'verification/SS_EXACT_COMPARISON.json', 'examples/query.json',
            'examples/pool.json', 'examples/EXPECTED.json')
for name in required:
    assert (root / name).is_file(), name
freeze = verify_freeze()
result = json.loads((root / 'results/EVALUATION.json').read_text(encoding='utf-8'))
assert result['all_checks_passed']
for name in ('strict', 'v012'):
    assert json.loads((root / f'verification/{name}/VERIFICATION.json').read_text(encoding='utf-8'))['status'] == 'passed'
assert json.loads((root / 'verification/SS_EXACT_COMPARISON.json').read_text(encoding='utf-8'))['all_equal']
repeat = json.loads((root / 'verification/REPEATABILITY.json').read_text(encoding='utf-8'))
assert repeat['source_freeze'] == freeze and repeat['two_full_evaluations']
assert len(repeat['files']) == 16 and all(r['equal'] for r in repeat['files'])
baseline = json.loads((root / 'verification/PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
assert json.loads((root / 'verification/PRESERVATION_CHECK.json').read_text(encoding='utf-8'))['all_preserved']
assert len(baseline['files']) == 4993
assert all(sha(root.parent / name) == value for name, value in baseline['files'].items())
files = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
         if p.is_file() and '__pycache__' not in p.parts and p.name != 'RELEASE_MANIFEST.json'}
manifest = {'release': root.name, 'source_freeze': freeze,
            'result_digest': result['result_digest'], 'files': files}
archive = root.parent / (root.name + '.zip')
record_path = root.parent / (root.name + '-ARCHIVE.json')
assert not archive.exists() and not record_path.exists() and not (root / 'RELEASE_MANIFEST.json').exists()
with (root / 'RELEASE_MANIFEST.json').open('x', encoding='utf-8') as f:
    f.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            z.write(p, root.name + '/' + p.relative_to(root).as_posix(),
                    compress_type=zipfile.ZIP_STORED if p.suffix == '.zip' else zipfile.ZIP_DEFLATED)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(set(n.casefold() for n in z.namelist())) == len(z.namelist())
    actual = {n[len(root.name) + 1:]: hashlib.sha256(z.read(n)).hexdigest()
              for n in z.namelist() if n != root.name + '/RELEASE_MANIFEST.json'}
    assert actual == files
record = {'archive': archive.name, 'sha256': sha(archive), 'bytes': archive.stat().st_size,
          'files': len(files) + 1, 'manifest_files': len(files),
          'source_freeze': freeze, 'result_digest': result['result_digest']}
with record_path.open('x', encoding='utf-8') as f:
    f.write(json.dumps(record, indent=2) + '\n')
print(json.dumps(record), flush=True)
