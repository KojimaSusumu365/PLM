import hashlib,json,os,sys,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs'/'PLM-L1-v0.9'
sys.path.insert(0,str(root))
from evaluation.integrity import sha,verify_freeze
from plm_l1_v09.component.algebra import digest
freeze=verify_freeze()
files={p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='RELEASE_MANIFEST.json'}
manifest={'release':'PLM-L1-v0.9','source_freeze':freeze,'result_digest':json.loads((root/'results/EVALUATION.json').read_text(encoding='utf-8'))['result_digest'],'files':files}
with (root/'RELEASE_MANIFEST.json').open('x',encoding='utf-8') as f: f.write(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
archive=root.parent/(root.name+'.zip')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(root.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            z.write(p,root.name+'/'+p.relative_to(root).as_posix(),compress_type=zipfile.ZIP_STORED if p.suffix=='.zip' else zipfile.ZIP_DEFLATED)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    actual={n[len(root.name)+1:]:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n!=root.name+'/RELEASE_MANIFEST.json'}
    assert actual==files
record={'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files)+1,'manifest_files':len(files),'source_freeze':freeze,'result_digest':manifest['result_digest']}
with (root.parent/'PLM-L1-v0.9-ARCHIVE.json').open('x',encoding='utf-8') as f: f.write(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
