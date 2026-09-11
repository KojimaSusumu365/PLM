from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from plm_c2 import render_markdown, run_suite
from plm_c2.evaluation import first_run_signature


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate PLM-C2 v0.4.")
    parser.add_argument("--json-out", default="EVALUATION_RESULTS.json")
    parser.add_argument("--report-out", default="EVALUATION_REPORT.md")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--record-first", action="store_true", help="Record the first frozen holdout result, without overwriting any prior record")
    args = parser.parse_args()

    suite = run_suite(bootstrap_samples=args.bootstrap_samples)
    if args.record_first:
        if not suite["freeze"]["valid"]:
            raise SystemExit("Cannot record a first run without a valid runtime freeze")
        with (Path(__file__).resolve().parent / "FIRST_EVALUATION.json").open("x", encoding="utf-8") as handle:
            json.dump(first_run_signature(suite), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        suite["acceptance"]["first_holdout_run_reproduced"] = None
        suite["acceptance_passed"] = False
    report = render_markdown(suite)
    json_path = Path(args.json_out)
    report_path = Path(args.report_out)
    json_path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"acceptance": suite["acceptance"], "holdout_metrics": suite["holdout"]["v04"]["metrics"],
                      "holdout_semantics": suite["holdout"]["semantics_v04"]["rule_checked"]}, ensure_ascii=False))
    print(f"JSON: {json_path.resolve()}")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
