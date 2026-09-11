import hashlib,json
from pathlib import Path
outputs=Path(__file__).resolve().parents[1]/'outputs'
files={}
for p in sorted(outputs.rglob('*')):
    relative=p.relative_to(outputs)
    if not p.is_file() or relative.parts[0].startswith('PLM-L1-v0.13') or relative.as_posix()=='PLM-SS-LANGUAGE-DIRECTION.md' or '__pycache__' in p.parts:
        continue
    with p.open('rb') as f:files[relative.as_posix()]=hashlib.file_digest(f,'sha256').hexdigest()
with (outputs/'PLM-L1-v0.13/verification/PRESERVED_BASELINE.json').open('x',encoding='utf-8') as f:
    f.write(json.dumps({'files':files,'shared_history_excluded':'PLM-SS-LANGUAGE-DIRECTION.md append only'},indent=2)+'\n')
print('preserved baseline',len(files))
