"""Record independent full numeric rerun and already-completed verification."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / 'outputs' / 'PLM-L1-v0.8'
REPEAT = WORK / 'v08-evaluation-repeat'
VERIFIED = WORK / 'v08-full-verification'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


first = ROOT / 'results'
comparisons = {}
for name in ('EVALUATION.json', 'REPORT.md', 'model/model.json', 'model/component/model.json'):
    left, right = first / name, REPEAT / name
    assert left.read_bytes() == right.read_bytes(), name
    comparisons[name] = {'bytes_equal': True, 'sha256': sha(left), 'bytes': left.stat().st_size}
for name in ('model/weights.npz', 'model/component/weights.npz'):
    left, right = first / name, REPEAT / name
    with np.load(left, allow_pickle=False) as a, np.load(right, allow_pickle=False) as b:
        assert set(a.files) == set(b.files), name
        arrays = {}
        for key in sorted(a.files):
            assert a[key].dtype == b[key].dtype and a[key].shape == b[key].shape
            assert np.array_equal(a[key], b[key]), (name, key)
            arrays[key] = {'dtype': str(a[key].dtype), 'shape': list(a[key].shape),
                           'sha256': hashlib.sha256(a[key].tobytes()).hexdigest(), 'equal': True}
    comparisons[name] = {'array_inventory_and_values_equal': True, 'arrays': arrays,
                         'first_container_sha256': sha(left), 'second_container_sha256': sha(right),
                         'container_bytes_equal': left.read_bytes() == right.read_bytes()}
result = read(first / 'EVALUATION.json')
verification = read(VERIFIED / 'VERIFICATION.json')
assert verification['status'] == 'passed' and not verification['preflight_boundary_only']
assert verification['result_digest'] == result['result_digest']
assert len(result['checks']) == verification['acceptance_checks'] == 456
assert all(row['passed'] for row in result['checks'])
assert sum(verification['test_counts'].values()) == 441
record = {'status': 'passed', 'complete_numeric_runs': 2, 'split': result['split'],
          'source_freeze': result['freeze_hash'], 'result_digest': result['result_digest'],
          'model_fingerprint': result['standard'][0]['fingerprint'],
          'acceptance_checks_each_run': len(result['checks']),
          'comparisons': comparisons, 'python': sys.version, 'numpy': np.__version__,
          'first_run': 'results/', 'second_run_workspace_record': 'work/v08-evaluation-repeat/',
          'scope': 'Same frozen data, protocol and seeds; independent complete rerun, not statistical replication with fresh data.'}
for source in sorted(VERIFIED.iterdir()):
    if source.is_file() and (source.suffix == '.log' or source.name == 'VERIFICATION.json'):
        target = ROOT / 'verification' / source.name
        assert not target.exists(), str(target)
        shutil.copyfile(source, target)
write(ROOT / 'verification' / 'REPRODUCIBILITY.json', record)
baseline = read(ROOT / 'verification' / 'PRESERVED_BASELINE.json')
assert all(sha(ROOT.parent / name) == wanted for name, wanted in baseline.items())
write(ROOT / 'verification' / 'PRESERVATION.json',
      {'status': 'unchanged', 'files': len(baseline),
       'scope': 'All prior files listed in PRESERVED_BASELINE.json, including the previous Claude review ZIP; shared direction-history Markdown excluded from that baseline.'})
lines = []
for mode in ('bound', 'partitioned'):
    rows = [r for r in result['standard'] if r['mode'] == mode]
    values = []
    for stage in ('read', 'generate', 'roundtrip'):
        counts = {k: sum(r['counts'][stage][k] for r in rows)
                  for k in ('requests', 'exact', 'wrong', 'abstained')}
        values.append(f"{counts['exact']:,}/{counts['requests']:,}")
        assert counts['wrong'] == counts['abstained'] == 0
    lines.append('|' + mode + '|' + '|'.join(values) + '|')
decision = (WORK / 'v08-release-decision-template.md').read_text(encoding='utf-8')
for key, value in {'@STANDARD_TABLE@': '\n'.join(lines),
                   '@RESULT_DIGEST@': result['result_digest'],
                   '@MODEL_FINGERPRINT@': result['standard'][0]['fingerprint'],
                   '@SOURCE_FREEZE@': result['freeze_hash'],
                   '@PRESERVED_FILES@': str(len(baseline))}.items():
    decision = decision.replace(key, value)
assert '@STANDARD_TABLE@' not in decision
with (ROOT / 'results' / 'RELEASE_DECISION.md').open('x', encoding='utf-8') as stream:
    stream.write(decision)
print(json.dumps({'status': 'passed', 'complete_numeric_runs': 2,
                  'acceptance_checks': 456, 'tests': 441,
                  'result_digest': result['result_digest'],
                  'model_fingerprint': result['standard'][0]['fingerprint']}, indent=2))
