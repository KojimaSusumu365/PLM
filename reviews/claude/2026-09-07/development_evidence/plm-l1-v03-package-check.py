"""Verify actual ZIP in a new extraction, leaving the released bytes untouched."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

WORK = Path(__file__).resolve().parent
OUTPUTS = WORK.parent / "outputs"
SOURCE = OUTPUTS / "PLM-L1-v0.3"
ARCHIVE = OUTPUTS / "PLM-L1-v0.3.zip"
EXTRACT = WORK / "plm-l1-v03-package-extracted"
VERIFY = WORK / "plm-l1-v03-package-verification"


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}


assert not EXTRACT.exists() and not VERIFY.exists()
assert EXTRACT.resolve().is_relative_to(WORK.resolve())
expected = snapshot(SOURCE)
archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
EXTRACT.mkdir()
with zipfile.ZipFile(ARCHIVE) as archive:
    for member in archive.infolist():
        assert (EXTRACT / member.filename).resolve().is_relative_to(EXTRACT.resolve())
    assert archive.testzip() is None
    archive.extractall(EXTRACT)
extracted = EXTRACT / SOURCE.name
assert snapshot(extracted) == expected
env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
env.pop("PYTHONPATH", None)
execution = subprocess.run([sys.executable, "-B", "verify_release.py", "--out", str(VERIFY)], cwd=extracted, env=env, capture_output=True, text=True, encoding="utf-8", timeout=240)
(WORK / "plm-l1-v03-package-verification.log").write_text(execution.stdout + execution.stderr, encoding="utf-8")
if execution.returncode:
    raise ValueError("ZIP verification failed: " + execution.stderr)
packet = extracted / "CLI_TEMP_PACKET.json"
direct = extracted / "CLI_DIRECT_PACKET.json"
assert not packet.exists() and not direct.exists()
assert packet.resolve().parent == extracted.resolve() and direct.resolve().parent == extracted.resolve()
try:
    commands = [
        ["-m", "plm_l1_v03", "read", "--model", "results/writer", "--text", "太郎が花子を助けた。", "--out", packet.name],
        ["-m", "plm_l1_v03", "generate", "--model", "results/writer", "--packet", packet.name],
        ["-m", "plm_l1_v03", "encode", "--model", "results/writer", "--meaning", "examples/MEANING.json", "--out", direct.name],
        ["-m", "plm_l1_v03", "generate", "--model", "results/writer", "--packet", direct.name],
        ["-c", "from evaluate import verify_freeze; print(verify_freeze())"],
    ]
    for i, command in enumerate(commands):
        executed = subprocess.run([sys.executable, "-B", *command], cwd=extracted, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        if executed.returncode:
            raise ValueError("CLI failed: " + executed.stdout + executed.stderr)
        if i in (1, 3):
            assert json.loads(executed.stdout)["text"] == "花子を太郎が助けた。"
finally:
    # Only exact, previously absent files created by this helper are removed.
    for target in (packet, direct):
        if target.exists():
            target.unlink()
assert snapshot(extracted) == expected and snapshot(SOURCE) == expected
assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == archive_hash
record = json.loads((VERIFY / "VERIFICATION.json").read_text(encoding="utf-8"))
record.update(archive=str(ARCHIVE), archive_sha256=archive_hash, archive_bytes=ARCHIVE.stat().st_size,
              archive_files=len(expected), extracted_bytes_equal=True, source_and_archive_unchanged=True,
              convenience_read_generate_cli_passed=True, direct_encode_generate_cli_passed=True, root_json_source_guard_passed=True)
with (OUTPUTS / "PLM-L1-v0.3-VERIFICATION.json").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(record, ensure_ascii=False, indent=2))
