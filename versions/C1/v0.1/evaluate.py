from __future__ import annotations

import argparse
import json
from pathlib import Path

from plm_c1 import render_markdown, run_suite


def main():
    parser = argparse.ArgumentParser(description="Evaluate PLM-C1 v0.1.")
    parser.add_argument("--json-out", default="EVALUATION_RESULTS.json")
    parser.add_argument("--report-out", default="EVALUATION_REPORT.md")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args()

    suite = run_suite(bootstrap_samples=args.bootstrap_samples)
    report = render_markdown(suite)
    json_path = Path(args.json_out)
    report_path = Path(args.report_out)
    json_path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"JSON: {json_path.resolve()}")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
