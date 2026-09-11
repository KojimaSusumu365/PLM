"""Package once; preserve initial outputs; extract and compare every file."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"work/PLM-P1-v0.2"
DEST=ROOT/"outputs/PLM-P1-v0.2"
ZIP=ROOT/"outputs/PLM-P1-v0.2.zip"
VERIFY=ROOT/"work/verify-p1-v02-package"
if any(p.exists() for p in (DEST,ZIP,VERIFY)):
    raise SystemExit("Refusing to overwrite existing release or verification directory")
verification=json.loads((SOURCE/"verification/VERIFICATION_RESULTS.json").read_text(encoding="utf-8"))
status=json.loads((SOURCE/"RELEASE_STATUS.json").read_text(encoding="utf-8"))
if not verification["functional_passed"]:
    raise SystemExit("Functional failure blocks packaging")
if status["numerical_acceptance_passed"]!=verification["checks"]["numerical_acceptance_passed"]:
    raise SystemExit("Release status mismatch")
shutil.copytree(SOURCE,DEST)
files={p.relative_to(DEST).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.rglob("*")) if p.is_file()}
(DEST/"RELEASE_MANIFEST.json").write_text(json.dumps({"version":"PLM-P1 v0.2","release_kind":status["release_kind"],"scope":"all files except this manifest","files":files},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
with zipfile.ZipFile(ZIP,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for path in sorted(DEST.rglob("*")):
        if path.is_file(): archive.write(path,path.relative_to(DEST.parent).as_posix())
VERIFY.mkdir()
with zipfile.ZipFile(ZIP) as archive:
    for entry in archive.infolist():
        if not (VERIFY/entry.filename).resolve().is_relative_to(VERIFY.resolve()):
            raise SystemExit("Invalid ZIP entry")
    archive.extractall(VERIFY)
    count=len(archive.infolist())
for name,checksum in files.items():
    if sha256((VERIFY/DEST.name/name).read_bytes()).hexdigest()!=checksum:
        raise SystemExit("Extracted file mismatch: "+name)
checksum=sha256(ZIP.read_bytes()).hexdigest()
(ROOT/"outputs/PLM-P1-v0.2.sha256").write_text(checksum+"  "+ZIP.name+"\n",encoding="utf-8")
print(json.dumps({"zip":str(ZIP),"bytes":ZIP.stat().st_size,"entries":count,"sha256":checksum,"extracted_files_match":True,"numerical_acceptance_passed":status["numerical_acceptance_passed"]},indent=2))
