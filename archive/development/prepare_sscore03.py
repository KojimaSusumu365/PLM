import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
release = root/'outputs/PLM-L1-SS-core-v0.3'
previous = release/'verification/PREVIOUS.json'
r = json.loads(previous.read_text(encoding='utf-8'))
for name in ('integrity.py', 'ports.py', 'faults.py'):
    p = release/'evaluation'/name
    r['copied']['evaluation/'+name] = hashlib.sha256(p.read_bytes()).hexdigest()
previous.write_text(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n', encoding='utf-8')
dev = root/'work/sscore03-dev'
shutil.copytree(dev, release/'development')
note = {'development_fixes': [
    'Initial trace detail used action as both label and score key; renamed score key before formal evaluation.',
    'Added finite demodulator/accumulator and positive-shape checks before freeze; no clean-score or threshold change.'
], 'thresholds_or_seeds_retuned': False, 'main_evaluation_read_before_freeze': False}
(release/'verification/DEVELOPMENT.json').write_text(json.dumps(note, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Prepared development evidence and copied-file hashes.')
