from __future__ import annotations

import argparse
import json
from pathlib import Path

from plm_c0 import (
    PLMC0Engine,
    PositiveLexicalBaseline,
    compare,
    evaluate,
    load_cases,
    render_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PLM-C0 v0.2 against a lexical baseline.")
    parser.add_argument("--dataset", help="Path to an evaluation dataset JSON file.")
    parser.add_argument("--json-out", default="EVALUATION_RESULTS.json")
    parser.add_argument("--report-out", default="EVALUATION_REPORT.md")
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    primary = evaluate(PLMC0Engine(), cases, "PLM-C0 v0.2")
    baseline = evaluate(PositiveLexicalBaseline(), cases, "positive lexical baseline")
    result = compare(primary, baseline)

    json_path = Path(args.json_out)
    report_path = Path(args.report_out)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(result), encoding="utf-8")

    print(render_markdown(result))
    print(f"JSON: {json_path.resolve()}")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
