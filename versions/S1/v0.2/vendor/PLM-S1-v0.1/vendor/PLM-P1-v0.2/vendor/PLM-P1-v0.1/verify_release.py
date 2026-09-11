"""P1 tests, unchanged R1/C2 replay, evaluation replay and actual CLI packet roundtrip."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from freeze_release import verify
from plm_p1.core import digest
from plm_p1.__main__ import load_json, write_json
from plm_p1.adapter import VENDOR, verify_dependency

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(ROOT / "verification"))
    args = parser.parse_args()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    frozen = verify()
    if not frozen["valid"]:
        raise SystemExit("Source freeze mismatch: " + str(frozen["differences"]))
    dependency = verify_dependency()
    before = {p.relative_to(VENDOR).as_posix(): sha256(p.read_bytes()).hexdigest() for p in VENDOR.rglob("*") if p.is_file()}
    def run(arguments, cwd, filename):
        result = subprocess.run([sys.executable, "-B", *arguments], cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
        text = result.stdout + result.stderr
        (out / filename).write_text(text, encoding="utf-8")
        if result.returncode:
            print(text)
            raise SystemExit("Failed: " + filename)
        return text
    log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], ROOT, "P1_TEST_OUTPUT.txt")
    p1_count = int(re.search(r"Ran (\d+) tests?", log).group(1))
    if "FAILED" in log or "skipped=" in log:
        raise SystemExit("Failed/skipped P1 tests")
    run(["verify_release.py", "--out-dir", str(out / "R1_C2_REPLAY")], VENDOR, "R1_C2_REPLAY_OUTPUT.txt")
    previous = load_json(out / "R1_C2_REPLAY" / "VERIFICATION_RESULTS.json")
    run(["evaluate.py", "--split", "evaluation", "--out-dir", str(out / "P1_EVALUATION_REPLAY")], ROOT, "P1_EVALUATION_REPLAY_OUTPUT.txt")
    numerical = load_json(out / "P1_EVALUATION_REPLAY" / "EVALUATION_RESULTS.json")
    first = load_json(ROOT / "FIRST_EVALUATION.json")
    cli_checks = {}
    with tempfile.TemporaryDirectory(prefix="plm-p1-cli-") as temp:
        packet_path = Path(temp) / "packet.json"
        recovery_path = Path(temp) / "recovery.json"
        run(["-m", "plm_p1", "encode", "--input", str(ROOT / "examples" / "INPUT_FRAMES.json"), "--out", str(packet_path)], ROOT, "CLI_ENCODE.txt")
        run(["-m", "plm_p1", "validate-packet", "--packet", str(packet_path)], ROOT, "CLI_VALIDATE.txt")
        run(["-m", "plm_p1", "decode", "--packet", str(packet_path), "--query", str(ROOT / "examples" / "QUERY.json"), "--out", str(recovery_path)], ROOT, "CLI_DECODE.txt")
        recovery = load_json(recovery_path)
        truth = load_json(ROOT / "examples" / "INPUT_FRAMES.json")[0]["slots"]["subject"]
        cli_checks["cli_full_signal_roundtrip"] = recovery["selected"] == truth and recovery["eligible_for_inference"] is False
        run(["-m", "plm_p1", "decode", "--packet", str(ROOT / "examples" / "S1_OBSERVATION_PACKET.json"),
             "--query", str(ROOT / "examples" / "QUERY.json"), "--expected-codebook", str(ROOT / "examples" / "CODEBOOK.json"), "--out", str(recovery_path)], ROOT, "CLI_MASKED_DECODE.txt")
        recovery = load_json(recovery_path)
        cli_checks["cli_masked_demo_recovered"] = recovery["selected"] == truth and recovery["observed_components"] == 512
        invalid = load_json(ROOT / "examples" / "QUERY.json")
        invalid["gold"] = truth
        bad_path = Path(temp) / "bad_query.json"
        write_json(bad_path, invalid)
        rejected = subprocess.run([sys.executable, "-B", "-m", "plm_p1", "decode", "--packet", str(packet_path),
                                   "--query", str(bad_path), "--out", str(Path(temp) / "must_not_exist.json")], cwd=ROOT, capture_output=True)
        cli_checks["cli_gold_query_rejected"] = rejected.returncode == 2 and not (Path(temp) / "must_not_exist.json").exists()
    after = {p.relative_to(VENDOR).as_posix(): sha256(p.read_bytes()).hexdigest() for p in VENDOR.rglob("*") if p.is_file()}
    adapter_examples = load_json(ROOT / "examples" / "R1_ADAPTER_EXAMPLES.json")
    adapter_checks = [c for row in adapter_examples["cases"] for c in row["state_recovery_checks"]]
    checks = {"p1_tests_passed": p1_count > 0, "r1_c2_278_tests_and_acceptance_preserved": previous["total_tests"] == 278 and previous["acceptance_passed"],
              "dependency_bytes_unchanged": before == after, "source_freeze_valid": verify()["valid"],
              "first_evaluation_reproduced": digest(numerical) == first["result_hash"],
              "numerical_acceptance_passed": numerical["acceptance_passed"],
              "r1_state_adapter_checks_passed": bool(adapter_checks) and all(c["correct"] and c["eligible_for_inference"] is False for c in adapter_checks),
              "inference_and_ss_stay_disabled": numerical["inference_enabled"] is False and numerical["ss_demodulation_implemented"] is False,
              **cli_checks}
    result = {"version": "PLM-P1 v0.1", "tests": {"P1": p1_count, **previous["tests"]}, "total_tests": p1_count + previous["total_tests"],
              "dependency": dependency, "source_freeze": frozen, "checks": checks, "passed": all(checks.values()),
              "numerical_acceptance": numerical["acceptance"], "numerical_query_count": len(numerical["rows"]),
              "independent_semantic_evaluation": "not_performed", "ss_demodulation_implemented": False}
    write_json(out / "VERIFICATION_RESULTS.json", result)
    report = (f"# PLM-P1 v0.1 検証結果\n\nP1 {p1_count}件 + R1 92件 + C2 186件 = {result['total_tests']}件のテスト合格、skipなし。\n\n"
              f"統合チェック {sum(checks.values())}/{len(checks)}。初回数値評価の完全再現、前提版の無変更、CLI信号往復、正解を含む照会の拒否を確認。\n\n"
              f"人工数値評価 {len(numerical['rows'])}照会。これはテスト件数に追加していません。受入条件と失敗条件はresults/EVALUATION_REPORT.mdを参照。\n\n"
              "独立意味評価、SS復調器、物理回路、推論の開放は未実施。S1は接続契約と数値パケットの段階です。\n")
    (out / "VERIFICATION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"tests": result["tests"], "checks": checks}, ensure_ascii=True, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
