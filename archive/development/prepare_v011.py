import hashlib,json,shutil
from pathlib import Path
base=Path(__file__).resolve().parents[1];out=base/'outputs';root=out/'PLM-L1-v0.11'
assert not root.exists()
baseline={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='PLM-SS-LANGUAGE-DIRECTION.md'}
for name in ('plm_l1_v011','evaluation','tests','data','verification','vendor'):(root/name).mkdir(parents=True)
(root/'verification/PRESERVED_BASELINE.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(out/'PLM-L1-v0.10.zip',root/'vendor/PLM-L1-v0.10.zip')
print('preserved baseline',len(baseline))
