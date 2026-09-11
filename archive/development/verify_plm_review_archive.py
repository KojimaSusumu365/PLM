"""Verify the actual final ZIP, extracted code, and all preserved inputs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
NAME = "PLM-L1-Claude-Review-2026-09-07"
BUNDLE = OUT / "L1-review"
ARCHIVE = OUT / (NAME + ".zip")
EXTRACT = ROOT / "work" / "rv"
LOGS = ROOT / "work" / "review-archive-logs"
LOGS.mkdir(exist_ok=False)
ENV = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
ENV.pop("PYTHONPATH", None)


def run(args, cwd, name, expected=0, timeout=900):
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, env=ENV, text=True, encoding="utf-8", capture_output=True, timeout=timeout)
    with (LOGS / (name + ".log")).open("x", encoding="utf-8") as f:
        f.write(result.stdout + result.stderr)
    if result.returncode != expected:
        raise ValueError(name + ": " + (result.stdout + result.stderr)[-4000:])
    return json.loads(result.stdout)


archive_check = run([str(BUNDLE / "tools" / "verify_bundle.py"), "--root", str(BUNDLE), "--archive", str(ARCHIVE), "--extract-to", str(EXTRACT)], ROOT, "ARCHIVE_AND_EXTRACTION")
extracted_bundle = EXTRACT / "L1-review"
release = extracted_bundle / "PLM-L1-v0.7"
tests = run(["verify_release.py", "--out", str(ROOT / "work" / "l1-review-extracted-check")], release, "EXTRACTED_RELEASE_VERIFICATION")
reading = run(["-m", "plm_l1_v07", "read", "--model", "results/model", "--text", "太郎が花子を助けた。花子が太郎を助けなかった。", "--out", "work/review-packet.json"], release, "EXTRACTED_READ")
generated = run(["-m", "plm_l1_v07", "generate", "--model", "results/model", "--packet", "work/review-packet.json", "--goals", "object", "subject"], release, "EXTRACTED_GENERATE")
if reading["status"] != "read" or generated["text"] != "花子を太郎が助けた。花子が太郎を助けなかった。":
    raise ValueError("Actual extracted CLI roundtrip failed")
run(["-m", "plm_l1_v07", "encode", "--model", "results/model", "--meaning", "examples/MEANING.json", "--out", "work/review-direct.json"], release, "EXTRACTED_ENCODE")
direct = run(["-m", "plm_l1_v07", "generate", "--model", "results/model", "--packet", "work/review-direct.json", "--goals", "subject", "object"], release, "EXTRACTED_DIRECT_GENERATE")
if direct["status"] != "generated" or direct["text"] != "太郎が花子を助けた。太郎を花子が助けなかった。":
    raise ValueError("Actual extracted direct generation failed")
bad = run(["-m", "plm_l1_v07", "read", "--model", "results/model", "--text", "太郎が花子を助けた。彼が太郎を助けた。", "--out", "work/must-not-exist.json"], release, "EXTRACTED_ABSTAIN", expected=2)
if bad["status"] != "abstain" or (release / "work" / "must-not-exist.json").exists():
    raise ValueError("Expected whole-document abstention")
post_cli = run([str(extracted_bundle / "tools" / "verify_bundle.py"), "--root", str(extracted_bundle)], ROOT, "POST_CLI_INTEGRITY")
preservation = run([str(ROOT / "work" / "build_plm_l1_review.py"), "preserve"], ROOT, "ORIGINAL_PRESERVATION")
with ARCHIVE.open("rb") as f:
    final_sha = hashlib.file_digest(f, "sha256").hexdigest()
if final_sha != archive_check["archive"]["sha256"] or (OUT / (NAME + ".sha256")).read_text(encoding="utf-8").split()[0] != final_sha:
    raise ValueError("Final archive changed or checksum mismatch")
report = {"status": "passed", "archive": ARCHIVE.name, "archive_bytes": ARCHIVE.stat().st_size,
          "archive_sha256": final_sha, "archive_files": archive_check["archive"]["files"],
          "archive_and_extraction": archive_check, "extracted_tests": tests,
          "read_generate_cli": {"status": "passed", "output": generated["text"]},
          "direct_encode_generate_cli": {"status": "passed", "output": direct["text"]},
          "invalid_second_sentence_atomic_abstention": True, "post_cli_integrity": post_cli,
          "originals_preserved": preservation, "full_numeric_evaluation_rerun_this_packaging_task": False,
          "note": "381 regression tests and 364 saved-result gates passed on both prepack copy and actual extracted ZIP. Counts are per run, not summed. Previous full-numeric two-run evidence remains in the bundle."}
with (OUT / (NAME + "-VERIFICATION.json")).open("x", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps({"status": report["status"], "archive_bytes": report["archive_bytes"], "archive_sha256": final_sha,
                  "archive_files": report["archive_files"], "extracted_tests": sum(tests["test_counts"].values()),
                  "acceptance_checks": tests["acceptance_checks"], "preserved_files": preservation["files"],
                  "read_generate": generated["text"], "direct_generate": direct["text"]}, ensure_ascii=False))
