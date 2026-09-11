"""Workspace-only archive validation helper; never edits existing releases."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

WORK = Path(__file__).resolve().parent
OUTPUTS = WORK.parent / "outputs"
ARCHIVE = OUTPUTS / "PLM-L1-v0.1.zip"
SOURCE = OUTPUTS / "PLM-L1-v0.1"
EXTRACT = WORK / "plm-l1-package-extracted"
VERIFY = WORK / "plm-l1-package-verification"


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


if EXTRACT.exists() or VERIFY.exists():
    raise ValueError("fresh verification directories required")
assert EXTRACT.resolve().is_relative_to(WORK.resolve())
expected = snapshot(SOURCE)
archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
EXTRACT.mkdir()
with zipfile.ZipFile(ARCHIVE) as archive:
    for member in archive.infolist():
        target = (EXTRACT / member.filename).resolve()
        if not target.is_relative_to(EXTRACT.resolve()):
            raise ValueError("archive path outside extraction directory")
    if archive.testzip() is not None:
        raise ValueError("archive CRC failure")
    archive.extractall(EXTRACT)
extracted = EXTRACT / SOURCE.name
if snapshot(extracted) != expected:
    raise ValueError("extracted file set or bytes mismatch")
env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
env.pop("PYTHONPATH", None)
verification = subprocess.run([sys.executable, "-B", "verify_release.py", "--out", str(VERIFY)], cwd=extracted,
                              env=env, text=True, encoding="utf-8", capture_output=True, timeout=180)
(WORK / "plm-l1-package-verification.log").write_text(verification.stdout + verification.stderr, encoding="utf-8")
if verification.returncode:
    raise ValueError("extracted verification failed: " + verification.stderr)
regression_packet = extracted / "CLI_TEMP_PACKET.json"
assert not regression_packet.exists() and regression_packet.resolve().parent == extracted.resolve()
try:
    reading = subprocess.run([sys.executable, "-B", "-m", "plm_l1", "read", "--model", "results/model", "--text", "太郎が花子を助けた。", "--out", regression_packet.name],
                             cwd=extracted, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if reading.returncode:
        raise ValueError("root packet CLI failed")
    guard = subprocess.run([sys.executable, "-B", "-c", "from evaluate import verify_freeze; print(verify_freeze())"], cwd=extracted,
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if guard.returncode:
        raise ValueError("root packet incorrectly invalidates source freeze: " + guard.stderr)
finally:
    # This exact file was absent before this check and created by our CLI.
    if regression_packet.exists():
        regression_packet.unlink()
if snapshot(extracted) != expected or snapshot(SOURCE) != expected or hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != archive_hash:
    raise ValueError("verification mutated release files")
record = json.loads((VERIFY / "VERIFICATION.json").read_text(encoding="utf-8"))
record.update(archive=str(ARCHIVE), archive_sha256=archive_hash, archive_bytes=ARCHIVE.stat().st_size,
              archive_files=len(expected), extracted_bytes_equal=True, source_and_archive_unchanged=True,
              cli_root_packet_source_guard_regression_passed=True)
(OUTPUTS / "PLM-L1-v0.1-VERIFICATION.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, ensure_ascii=False, indent=2))
