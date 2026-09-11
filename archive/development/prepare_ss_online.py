import hashlib
import json
import shutil
from pathlib import Path
workspace=Path(__file__).resolve().parents[1]
outputs=workspace/'outputs'
target=outputs/'PLM-L1-SS-online-v0.1'
target.mkdir(exist_ok=False)
for name in ('ss_online','evaluation','data','tests','verification','vendor'):
    (target/name).mkdir()
shutil.copyfile(outputs/'PLM-L1-v0.13/plm_l1_v013/algebra.py',target/'ss_online/algebra.py')
shutil.copyfile(outputs/'PLM-L1-SS-weighting-v0.1.zip',target/'vendor/PLM-L1-SS-weighting-v0.1.zip')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
previous={p.relative_to(outputs).as_posix():sha(p) for p in sorted(outputs.rglob('*')) if p.is_file() and not p.is_relative_to(target) and '__pycache__' not in p.parts}
copied={p.relative_to(target).as_posix():sha(p) for p in target.rglob('*') if p.is_file()}
with (target/'verification/BASELINE.json').open('x',encoding='utf-8') as f:json.dump({'previous_files':previous,'copied_files':copied},f,indent=2)
print(json.dumps({'root':str(target),'preserved_files':len(previous)}))
