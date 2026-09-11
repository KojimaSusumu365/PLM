"""Verify actual ZIP in a new extraction, leaving all released bytes untouched."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

WORK = Path(__file__).resolve().parent
OUTPUTS = WORK.parent / "outputs"
SOURCE = OUTPUTS / "PLM-L1-v0.6"
ARCHIVE = OUTPUTS / "PLM-L1-v0.6.zip"
EXTRACT = WORK / "plm-l1-v06-package-extracted"
VERIFY = WORK / "plm-l1-v06-package-verification"


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}


assert not EXTRACT.exists() and not VERIFY.exists()
assert EXTRACT.resolve().is_relative_to(WORK.resolve())
expected = snapshot(SOURCE)
archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
EXTRACT.mkdir()
with zipfile.ZipFile(ARCHIVE) as archive:
    names = [member.filename for member in archive.infolist()]
    assert len(set(names)) == len(names)
    for member in archive.infolist():
        assert member.filename.startswith(SOURCE.name + "/")
        assert (EXTRACT / member.filename).resolve().is_relative_to(EXTRACT.resolve())
    assert archive.testzip() is None
    archive.extractall(EXTRACT)
extracted = EXTRACT / SOURCE.name
assert snapshot(extracted) == expected
env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
env.pop("PYTHONPATH", None)
execution = subprocess.run([sys.executable, "-B", "verify_release.py", "--out", str(VERIFY)], cwd=extracted, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)
(WORK / "plm-l1-v06-package-verification.log").write_text(execution.stdout + execution.stderr, encoding="utf-8")
if execution.returncode:
    raise ValueError("ZIP verification failed: " + execution.stdout + execution.stderr)
packet = extracted / "CLI_TEMP_PACKET.json"
direct = extracted / "CLI_DIRECT_PACKET.json"
assert not packet.exists() and not direct.exists()
assert packet.resolve().parent == extracted.resolve() and direct.resolve().parent == extracted.resolve()
try:
    commands = [
        ["-m", "plm_l1_v06", "read", "--model", "results/model", "--text", "花子を太郎が助けなかった。", "--out", packet.name],
        ["-m", "plm_l1_v06", "generate", "--model", "results/model", "--packet", packet.name, "--goal", "subject"],
        ["-m", "plm_l1_v06", "encode", "--model", "results/model", "--meaning", "examples/MEANING.json", "--out", direct.name],
        ["-m", "plm_l1_v06", "generate", "--model", "results/model", "--packet", direct.name, "--goal", "object"],
        ["-c", "from evaluate import verify_freeze; print(verify_freeze())"],
    ]
    for i, command in enumerate(commands):
        executed = subprocess.run([sys.executable, "-B", *command], cwd=extracted, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        if executed.returncode:
            raise ValueError("CLI failed: " + executed.stdout + executed.stderr)
        if i == 1:
            assert json.loads(executed.stdout)["text"] == "太郎が花子を助けなかった。"
        elif i == 3:
            assert json.loads(executed.stdout)["text"] == "花子を太郎が助けなかった。"
finally:
    # Only exact, previously absent JSON files created by this helper.
    for target in (packet, direct):
        if target.exists():
            assert target.resolve().parent == extracted.resolve()
            target.unlink()
assert snapshot(extracted) == expected and snapshot(SOURCE) == expected
assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == archive_hash
record = json.loads((VERIFY / "VERIFICATION.json").read_text(encoding="utf-8"))
record.update(archive=str(ARCHIVE), archive_sha256=archive_hash, archive_bytes=ARCHIVE.stat().st_size,
              archive_files=len(expected), extracted_bytes_equal=True, source_and_archive_unchanged=True,
              heldout_read_generate_cli_passed=True, direct_encode_heldout_generate_cli_passed=True, source_freeze_checked_after_cli=True)
with (OUTPUTS / "PLM-L1-v0.6-VERIFICATION.json").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(record, ensure_ascii=False, indent=2))
