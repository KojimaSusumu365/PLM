"""One-shot package and safely bounded extraction; refuse existing release targets."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import zipfile

BASE=Path(__file__).resolve().parents[1]
SOURCE=BASE/"work/PLM-S1-v0.1"
DEST=BASE/"outputs/PLM-S1-v0.1"
ZIP=BASE/"outputs/PLM-S1-v0.1.zip"
CHECK=BASE/"work/verify-s1-v01-package"
if any(p.exists() for p in (DEST,ZIP,CHECK)): raise SystemExit("Refusing to overwrite release or verification directory")
status=json.loads((SOURCE/"RELEASE_STATUS.json").read_text(encoding="utf-8"))
v=json.loads((SOURCE/"verification/VERIFICATION_RESULTS.json").read_text(encoding="utf-8"))
if not v["functional_passed"] or not v["full_s1_replay_matches"]: raise SystemExit("Functional/full-replay failure blocks packaging")
if status["numerical_acceptance_passed"]!=v["checks"]["numerical_acceptance_passed"]: raise SystemExit("Status mismatch")
shutil.copytree(SOURCE,DEST)
files={p.relative_to(DEST).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.rglob("*")) if p.is_file()}
(DEST/"RELEASE_MANIFEST.json").write_text(json.dumps({"version":"PLM-S1 v0.1","release_kind":status["release_kind"],"scope":"all files except this manifest","files":files},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
with zipfile.ZipFile(ZIP,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for p in sorted(DEST.rglob("*")):
        if p.is_file(): archive.write(p,p.relative_to(DEST.parent).as_posix())
CHECK.mkdir()
with zipfile.ZipFile(ZIP) as archive:
    for entry in archive.infolist():
        if not (CHECK/entry.filename).resolve().is_relative_to(CHECK.resolve()): raise SystemExit("Unsafe ZIP entry")
    archive.extractall(CHECK)
    count=len(archive.infolist())
for name,expected in files.items():
    if sha256((CHECK/DEST.name/name).read_bytes()).hexdigest()!=expected: raise SystemExit("Extraction mismatch: "+name)
checksum=sha256(ZIP.read_bytes()).hexdigest()
(BASE/"outputs/PLM-S1-v0.1.sha256").write_text(checksum+"  "+ZIP.name+"\n",encoding="utf-8")
print(json.dumps({"zip":str(ZIP),"bytes":ZIP.stat().st_size,"entries":count,"sha256":checksum,"extracted_files_match":True},indent=2))
