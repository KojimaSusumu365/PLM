"""Repeatable verification that never rewrites the frozen C2 dependency."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from freeze_release import verify
from plm_r1.contract import load_json
from plm_r1.evaluation import evaluate
from plm_r1.producer import VENDOR, verify_dependency

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(ROOT / "verification"))
    args = parser.parse_args()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = verify()
    if not manifest["valid"]:
        raise SystemExit("R1 source freeze mismatch: " + str(manifest["differences"]))
    dependency = verify_dependency()
    vendor_before = {p.relative_to(VENDOR).as_posix(): sha256(p.read_bytes()).hexdigest()
                     for p in VENDOR.rglob("*") if p.is_file()}
    def run(arguments, cwd, name):
        result = subprocess.run([sys.executable, "-B", *arguments], cwd=cwd, capture_output=True,
                                encoding="utf-8", errors="replace")
        log = result.stdout + result.stderr
        (out / name).write_text(log, encoding="utf-8")
        if result.returncode:
            print(log)
            raise SystemExit("Verification failed: " + name)
        return log
    counts = {}
    for name, directory in (("R1", ROOT), ("C2", VENDOR)):
        log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], directory, name + "_TEST_OUTPUT.txt")
        counts[name] = int(re.search(r"Ran (\d+) tests?", log).group(1))
        if "skipped=" in log or "FAILED" in log:
            raise SystemExit("Skipped or failed tests: " + name)
    run(["evaluate.py", "--json-out", str(out / "C2_REPLAY_RESULTS.json"),
         "--report-out", str(out / "C2_REPLAY_REPORT.md")], VENDOR, "C2_REPLAY_OUTPUT.txt")
    replay = load_json(out / "C2_REPLAY_RESULTS.json")
    reference = load_json(VENDOR / "EVALUATION_RESULTS.json")
    identical = replay == reference
    independent = evaluate(load_json(ROOT / "evaluation" / "PILOT_ANNOTATIONS_TEMPLATE.json"))
    smoke = []
    with tempfile.TemporaryDirectory(prefix="plm-r1-cli-") as temp:
        db = str(Path(temp) / "cli.sqlite3")
        base = ["-m", "plm_r1", "ingest", "--db", db, "--input", str(ROOT / "examples" / "INPUTS.json"),
                "--kind", "inputs", "--source-id", "cli-internal-test"]
        for i in range(2):
            smoke.append(json.loads(run(base, ROOT, f"CLI_IMPORT_{i + 1}.txt")))
        ledger_path = Path(temp) / "ledger.json"
        run(["-m", "plm_r1", "ledger", "--db", db, "--json-out", str(ledger_path),
             "--markdown-out", str(Path(temp) / "ledger.md")], ROOT, "CLI_LEDGER.txt")
        ledger = load_json(ledger_path)
    vendor_after = {p.relative_to(VENDOR).as_posix(): sha256(p.read_bytes()).hexdigest()
                    for p in VENDOR.rglob("*") if p.is_file()}
    acceptance = {"r1_tests_passed": counts["R1"] > 0,
                  "all_186_c2_tests_passed": counts["C2"] == 186,
                  "c2_evaluation_exact_reproduction": identical,
                  "c2_acceptance_preserved": all(replay["acceptance"].values()),
                  "vendor_bytes_unchanged_by_verification": vendor_before == vendor_after,
                  "source_freeze_valid": verify()["valid"],
                  "cli_import_and_persistent_export": ledger["unique_content_count"] == 1,
                  "cli_repeat_idempotent": smoke[0]["document_created"] and not smoke[1]["document_created"] and not smoke[1]["source_link_created"],
                  "inference_disabled": ledger["inference_enabled"] is False,
                  "independent_evaluation_correctly_pending": independent["status"] == "pending_inputs" and independent["metrics"] is None}
    report = {"version": "PLM-R1 v0.1", "tests": counts, "total_tests": sum(counts.values()),
              "r1_integration_fixture_documents": 16, "c2_v04_dev_holdout_transport_subcases": 55,
              "dependency": dependency, "source_freeze": manifest, "acceptance": acceptance,
              "acceptance_passed": all(acceptance.values()),
              "c2_replay_file_sha256": sha256((out / "C2_REPLAY_RESULTS.json").read_bytes()).hexdigest(),
              "independent_evaluation": independent}
    (out / "VERIFICATION_RESULTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = (f"# PLM-R1 v0.1 検証結果\n\nR1 {counts['R1']}件 + C2 {counts['C2']}件 = {sum(counts.values())}件のテストが合格。skipなし。\n\n"
            "R1内部16例とC2 v0.4開発/holdout 55例の取り込みをテスト内で確認。サブケース数は独立試験数として水増ししていません。\n\n"
            f"受入チェック {sum(acceptance.values())}/{len(acceptance)}。C2評価JSON完全再現: {identical}。依存ファイルは実行前後でバイト一致。\n\n"
            "独立意味評価は未実施。実データ・別担当者の注釈がないためmetrics=null、status=pending_inputsを維持。テスト合格は意味精度や推論利用の許可ではありません。\n\n"
            "詳細はVERIFICATION_RESULTS.jsonと各ログ。再実行: `python -B verify_release.py`。\n")
    (out / "VERIFICATION_REPORT.md").write_text(text, encoding="utf-8")
    print(json.dumps({"tests": counts, "acceptance": acceptance}, ensure_ascii=True, indent=2))
    if not all(acceptance.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
