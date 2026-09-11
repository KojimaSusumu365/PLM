"""One-shot local packaging; refuses overwriting an existing deliverable."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "PLM-R1-v0.1"
DESTINATION = ROOT / "outputs" / "PLM-R1-v0.1"
ZIP = ROOT / "outputs" / "PLM-R1-v0.1.zip"
VERIFY = ROOT / "work" / "verify-r1-v01-package"

if DESTINATION.exists() or ZIP.exists() or VERIFY.exists():
    raise SystemExit("Refusing to overwrite existing release or verification directory")
shutil.copytree(SOURCE, DESTINATION)
files = {p.relative_to(DESTINATION).as_posix(): sha256(p.read_bytes()).hexdigest()
         for p in sorted(DESTINATION.rglob("*")) if p.is_file()}
manifest = {"release": "PLM-R1 v0.1", "scope": "every package file except this manifest itself",
            "file_count": len(files), "files": files}
(DESTINATION / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
with zipfile.ZipFile(ZIP, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(DESTINATION.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(DESTINATION.parent).as_posix())
VERIFY.mkdir()
with zipfile.ZipFile(ZIP) as archive:
    for entry in archive.infolist():
        target = (VERIFY / entry.filename).resolve()
        if not target.is_relative_to(VERIFY.resolve()):
            raise ValueError("Invalid archive path")
    archive.extractall(VERIFY)
    entry_count = len(archive.infolist())
extracted = VERIFY / DESTINATION.name
for name, value in files.items():
    if sha256((extracted / name).read_bytes()).hexdigest() != value:
        raise SystemExit("Extracted file mismatch: " + name)
checksum = sha256(ZIP.read_bytes()).hexdigest()
(ROOT / "outputs" / "PLM-R1-v0.1.sha256").write_text(checksum + "  " + ZIP.name + "\n", encoding="utf-8")
print(json.dumps({"zip": str(ZIP), "bytes": ZIP.stat().st_size, "entries": entry_count,
                  "sha256": checksum, "extracted_files_match": True, "extracted_directory": str(extracted)}, indent=2))
