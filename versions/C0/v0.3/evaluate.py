from __future__ import annotations

import argparse
import json
from pathlib import Path

from plm_c0 import (
    EngineConfig,
    PLMC0Engine,
    PositiveLexicalBaseline,
    compare,
    evaluate,
    load_cases,
    render_markdown,
    validate_cases,
)


def run_model(engine, cases, name, bootstrap_samples):
    return evaluate(
        engine,
        cases,
        name,
        bootstrap_samples=bootstrap_samples,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PLM-C0 v0.3 benchmark and ablations.")
    parser.add_argument("--dataset", help="Path to a schema-v2 benchmark JSON file.")
    parser.add_argument("--json-out", default="EVALUATION_RESULTS.json")
    parser.add_argument("--report-out", default="EVALUATION_REPORT.md")
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    full_engine = PLMC0Engine()
    concept_domains = {
        concept_id: concept["domain"]
        for concept_id, concept in full_engine.concepts.items()
    }
    validation = validate_cases(cases, concept_domains)
    dev_cases = [case for case in cases if case["split"] == "dev"]
    test_cases = [case for case in cases if case["split"] == "test"]

    splits = {}
    for split_name, split_cases in (("dev", dev_cases), ("test", test_cases)):
        primary = run_model(
            PLMC0Engine(), split_cases, "PLM-C0 v0.3", args.bootstrap_samples
        )
        baseline = run_model(
            PositiveLexicalBaseline(), split_cases, "positive lexical baseline", args.bootstrap_samples
        )
        splits[split_name] = compare(
            primary, baseline, bootstrap_samples=args.bootstrap_samples
        )

    configurations = {
        "full": EngineConfig(),
        "no_negation": EngineConfig(use_negation=False),
        "no_context": EngineConfig(use_context=False),
        "no_hierarchy": EngineConfig(use_hierarchy=False),
        "no_sibling_contradiction": EngineConfig(use_sibling_contradiction=False),
        "no_overlap_suppression": EngineConfig(suppress_overlaps=False),
        "no_ascii_boundaries": EngineConfig(strict_ascii_boundaries=False),
    }
    ablations = {
        name: run_model(
            PLMC0Engine(config=config),
            test_cases,
            name,
            args.bootstrap_samples,
        )
        for name, config in configurations.items()
    }

    suite = {
        "version": "PLM-C0 v0.3",
        "dataset": {
            "name": "PLM-C0-v0.3-benchmark",
            "case_count": validation["case_count"],
            "dev_cases": validation["splits"]["dev"],
            "test_cases": validation["splits"]["test"],
            "template_groups": validation["template_groups"],
            "construction": "72 semantic seeds x 4 deterministic wrappers",
        },
        "splits": splits,
        "ablations": ablations,
    }

    json_path = Path(args.json_out)
    report_path = Path(args.report_out)
    report = render_markdown(suite)
    json_path.write_text(json.dumps(suite, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"JSON: {json_path.resolve()}")
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
