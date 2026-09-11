"""Preparation only; cannot overwrite a lock or previous release."""
import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
release=root/'outputs/PLM-L1-SS-active-v0.3'
sys.path.insert(0,str(release))
from evaluation.integrity import write,sha,freeze
old=root/'outputs/PLM-L1-SS-active-v0.2'
files={p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}
write(release/'verification/PREVIOUS_BASELINE.json',{'previous_release':'PLM-L1-SS-active-v0.2','files':files,
    'zip_sha256':sha(root/'outputs/PLM-L1-SS-active-v0.2.zip'),
    'copied_core':{name:sha(release/'ss_multicode'/name) for name in ['__init__.py','algebra.py','model.py','learning.py']}})
for name in ['__init__.py','algebra.py','model.py','learning.py']:
    assert sha(old/'ss_multicode'/name)==sha(release/'ss_multicode'/name)
print(json.dumps(freeze(),indent=2))
