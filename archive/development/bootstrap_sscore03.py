import hashlib, json, shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
old = root / 'outputs/PLM-L1-SS-core-v0.2'
new = root / 'outputs/PLM-L1-SS-core-v0.3'
new.mkdir(exist_ok=False)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
previous = {p.relative_to(old).as_posix(): sha(p) for p in old.rglob('*') if p.is_file()}
copied = {}
for folder in ('plm_l1_v09', 'ss_document', 'ss_partial', 'ss_revision', 'ss_retention',
               'ss_reconfirm', 'ss_core', 'ss_core_v02', 'bridge', 'vendor', 'model', 'tests'):
    for p in sorted((old / folder).rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc':
            q = new / p.relative_to(old)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
            copied[q.relative_to(new).as_posix()] = sha(p)
for folder in ('ss_core_v03', 'evaluation', 'verification', 'data'):
    (new / folder).mkdir()
for name in ('event_oracle.py', 'oracle.py'):
    shutil.copy2(old / 'evaluation' / name, new / 'evaluation' / name)
    copied['evaluation/' + name] = sha(old / 'evaluation' / name)
# Legacy tests reference a small subset of the inherited corpus files.
for p in (old / 'data').glob('*.json'):
    shutil.copy2(p, new / 'data' / p.name)
    copied['data/' + p.name] = sha(p)
record = {'source': old.name, 'previous_files': previous,
          'previous_zip_sha256': sha(root/'outputs/PLM-L1-SS-core-v0.2.zip'),
          'copied': copied}
(new/'verification/PREVIOUS.json').write_text(json.dumps(record, sort_keys=True, ensure_ascii=False)+'\n', encoding='utf-8')
print({'new': str(new), 'copied': len(copied), 'previous': len(previous)})
