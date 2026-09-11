import json,sys,zipfile
from pathlib import Path
WORK=Path(__file__).resolve().parent;ROOT=WORK.parent/'outputs/PLM-L1-SS-doc-v0.6';sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
verify();assert read(ROOT/'verification/DOCUMENT_QA.json')['passed']
archive=ROOT.with_name(ROOT.name+'.zip');extracted=WORK/'ssdoc06-zip-extracted'
assert not archive.exists() and not extracted.exists() and not (ROOT/'RELEASE_MANIFEST.json').exists()
files=sorted(p for p in ROOT.rglob('*') if p.is_file());assert not any('__pycache__' in p.parts or p.suffix=='.pyc' for p in files)
write(ROOT/'RELEASE_MANIFEST.json',{'files':{p.relative_to(ROOT).as_posix():sha(p) for p in files},'frozen_digest':verify(),'eligible_for_inference':False})
files=sorted(p for p in ROOT.rglob('*') if p.is_file())
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in files:z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix())
extracted.mkdir()
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))==len(files)
    for name in z.namelist():assert name.startswith(ROOT.name+'/') and (extracted/name).resolve().is_relative_to(extracted.resolve())
    z.extractall(extracted)
eroot=extracted/ROOT.name;hashes=lambda d:{p.relative_to(d).as_posix():sha(p) for p in d.rglob('*') if p.is_file()}
assert hashes(ROOT)==hashes(eroot)
record={'passed':True,'archive':str(archive),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,
        'uncompressed_bytes':sum(p.stat().st_size for p in files),'files':len(files),'manifest_files':len(files)-1,
        'manifest_sha256':sha(ROOT/'RELEASE_MANIFEST.json'),'extracted_root':str(eroot),'crc_ok':True,'all_extracted_bytes_equal':True}
write(WORK/'ssdoc06-package.json',record);print(json.dumps(record,indent=2),flush=True)
