"""Seal and actually extract a self-contained release; no overwrite of prior outputs."""
import json
import sys
import zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];release=root/'outputs/PLM-L1-SS-active-v0.3'
sys.path.insert(0,str(release))
from evaluation.integrity import sha,write,verify_freeze

verify_freeze()
verification=json.loads((root/'work/ss-active3-verify/VERIFY.json').read_text(encoding='utf-8'))
assert verification['passed']
write(release/'verification/RELEASE_VERIFY.json',verification)
assert json.loads((release/'verification/AUDIT.json').read_text(encoding='utf-8'))['passed']
files={p.relative_to(release).as_posix():sha(p) for p in release.rglob('*') if p.is_file()}
assert not any('__pycache__' in p for p in files)
write(release/'RELEASE_MANIFEST.json',{'schema':'plm-ss-active3-release-manifest','files':files,'self_excluded':True})
archive=root/'outputs/PLM-L1-SS-active-v0.3.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(release.rglob('*')):
        if p.is_file():z.write(p,arcname=release.name+'/'+p.relative_to(release).as_posix())
extracted=root/'work/ss-active3-zip-extracted';extracted.mkdir(exist_ok=False)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for info in z.infolist():
        target=(extracted/info.filename).resolve();assert target.is_relative_to(extracted.resolve())
    z.extractall(extracted)
unpacked=extracted/release.name
actual={p.relative_to(unpacked).as_posix():sha(p) for p in unpacked.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
assert files==actual
result={'zip':str(archive),'zip_sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(files)+1,
        'manifest_files':len(files),'extracted_directory':str(unpacked),'crc_passed':True,'extracted_manifest_passed':True,
        'freeze':verify_freeze()}
write(root/'work/ss-active3-package.json',result);print(json.dumps(result,indent=2))
