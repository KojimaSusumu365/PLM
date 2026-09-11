import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / 'outputs/PLM-L1-SS-doc-v0.1'
NEW = ROOT / 'outputs/PLM-L1-SS-doc-v0.2'


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


NEW.mkdir(exist_ok=False)
for name in ('ss_document', 'plm_l1_v09', 'data'):
    shutil.copytree(OLD / name, NEW / name, ignore=shutil.ignore_patterns('__pycache__'))
for name in ('ss_partial', 'evaluation', 'tests', 'verification', 'examples'):
    (NEW / name).mkdir()
shutil.copytree(OLD / 'results/models/s0-c0', NEW / 'model/document')
for name in ('oracle.py', 'event_oracle.py'):
    shutil.copy2(OLD / 'evaluation' / name, NEW / 'evaluation' / name)
shutil.copy2(OLD / 'requirements.txt', NEW / 'requirements.txt')
files = {p.relative_to(OLD).as_posix(): sha(p) for p in OLD.rglob('*') if p.is_file()}
baseline = {'release': OLD.name, 'files': files, 'zip_sha256': sha(OLD.with_name(OLD.name + '.zip')),
            'copied_source': {p.relative_to(NEW).as_posix(): sha(p) for package in ('ss_document', 'plm_l1_v09') for p in (NEW / package).rglob('*.py')}}
with (NEW / 'verification/PREVIOUS_BASELINE.json').open('x', encoding='utf-8') as f:
    json.dump(baseline, f, ensure_ascii=False, sort_keys=True, indent=2)
print(str(NEW))
