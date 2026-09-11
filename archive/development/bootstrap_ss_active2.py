import hashlib,json,shutil
from pathlib import Path
workspace=Path(__file__).resolve().parents[1]; outputs=workspace/'outputs'
root=outputs/'PLM-L1-SS-active-v0.2'; old=outputs/'PLM-L1-SS-active-v0.1'
assert not root.exists()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
previous={p.relative_to(outputs).as_posix():sha(p) for p in sorted(outputs.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
archive=outputs/(old.name+'.zip'); assert sha(archive)=='cdbfe39c88dccca72700a595f113771cbc40ce4b04f94230beac11aa7e297e56'
for name in ('ss_multicode','ss_active','evaluation','data','tests','verification','vendor'):(root/name).mkdir(parents=True)
copied={}
for name in ('__init__.py','algebra.py','model.py','learning.py'):
    p=root/'ss_multicode'/name;shutil.copyfile(old/'ss_multicode'/name,p);copied[p.relative_to(root).as_posix()]=sha(p)
shutil.copyfile(old/'ss_active/selection.py',root/'ss_active/base_selection.py')
copied['ss_active/base_selection.py']=sha(root/'ss_active/base_selection.py')
shutil.copyfile(archive,root/'vendor'/archive.name)
with (root/'verification/BASELINE.json').open('x',encoding='utf-8') as f:json.dump({'previous_files':previous,'copied_files':copied,'vendor_sha256':sha(archive)},f,ensure_ascii=False,indent=2)
print(json.dumps({'previous_files':len(previous),'copied_files':copied}))
