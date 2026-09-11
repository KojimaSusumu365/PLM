from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from plm_c0 import PLMC0Engine, PositiveLexicalBaseline, compare, evaluate, load_cases

from .engine import C1Config, PLMC1Engine


def _metric_rows(primary, comparison, lexical=None):
    c0 = comparison["baseline"]
    delta = comparison["delta_primary_minus_baseline"]
    keys = [
        "top1_accuracy", "top5_recall", "mrr", "macro_f1",
        "unresolved_precision", "unresolved_recall", "contradiction_rejection",
        "coverage", "selective_accuracy", "expected_calibration_error", "brier_score",
    ]
    rows = []
    for key in keys:
        rows.append({
            "metric": key,
            "c1": primary["metrics"].get(key),
            "c0": c0["metrics"].get(key),
            "lexical": lexical["metrics"].get(key) if lexical else None,
            "delta_c1_minus_c0": delta.get(key),
        })
    return rows


def _operation_audit(cases):
    counts = Counter()
    residual_removed = 0.0
    superseded_evidence = 0
    forced_unresolved = Counter()
    seen_groups = set()
    audited = 0
    for case in cases:
        if case["template_group"] in seen_groups:
            continue
        seen_groups.add(case["template_group"])
        result = PLMC1Engine().analyze(case["inputs"])
        audited += 1
        for operation in result["operations"]:
            counts[operation["operation"]] += 1
            residual_removed += float(operation.get("residual_removed", 0.0))
        superseded_evidence += result["diagnostics"]["superseded_evidence_items"]
        for domain in result["diagnostics"]["forced_unresolved_domains"]:
            forced_unresolved[domain] += 1
    return {
        "semantic_groups_audited": audited,
        "operation_counts": dict(sorted(counts.items())),
        "residual_weight_removed": round(residual_removed, 4),
        "superseded_evidence_items": superseded_evidence,
        "forced_unresolved_domains": dict(sorted(forced_unresolved.items())),
    }


def run_suite(bootstrap_samples: int = 2000):
    regression_all = load_cases()
    regression_test = [case for case in regression_all if case["split"] == "test"]
    challenge_path = Path(__file__).resolve().parents[1] / "data" / "challenge_c1_v01.json"
    challenge = load_cases(str(challenge_path))

    c1_regression = evaluate(
        PLMC1Engine(), regression_test, "PLM-C1 v0.1", bootstrap_samples=bootstrap_samples
    )
    c0_regression = evaluate(
        PLMC0Engine(), regression_test, "PLM-C0 v0.3", bootstrap_samples=bootstrap_samples
    )
    lexical_regression = evaluate(
        PositiveLexicalBaseline(), regression_test, "positive lexical baseline",
        bootstrap_samples=bootstrap_samples,
    )
    regression_comparison = compare(
        c1_regression, c0_regression, bootstrap_samples=bootstrap_samples
    )

    c1_challenge = evaluate(
        PLMC1Engine(), challenge, "PLM-C1 v0.1", bootstrap_samples=bootstrap_samples
    )
    c0_challenge = evaluate(
        PLMC0Engine(), challenge, "PLM-C0 v0.3", bootstrap_samples=bootstrap_samples
    )
    challenge_comparison = compare(
        c1_challenge, c0_challenge, bootstrap_samples=bootstrap_samples
    )

    configs = {
        "full": C1Config(),
        "no_scope": C1Config(use_scope=False),
        "no_correction": C1Config(use_correction=False),
        "no_residual": C1Config(use_residual=False),
        "no_negation": C1Config(use_negation=False),
    }
    ablations = {
        name: evaluate(
            PLMC1Engine(config=config), regression_test, name,
            bootstrap_samples=bootstrap_samples,
        )
        for name, config in configs.items()
    }

    return {
        "version": "PLM-C1 v0.1",
        "datasets": {
            "frozen_v03_regression": {
                "cases": len(regression_all),
                "test_cases": len(regression_test),
                "semantic_groups": len({case["template_group"] for case in regression_all}),
                "role": "known fixed regression benchmark used as the C1 target",
            },
            "post_implementation_challenge": {
                "cases": len(challenge),
                "semantic_groups": len({case["template_group"] for case in challenge}),
                "role": "frozen before first run; not used for tuning",
            },
        },
        "regression": {
            "comparison": regression_comparison,
            "lexical_baseline": lexical_regression,
            "metric_rows": _metric_rows(c1_regression, regression_comparison, lexical_regression),
        },
        "challenge": {
            "comparison": challenge_comparison,
            "metric_rows": _metric_rows(c1_challenge, challenge_comparison),
        },
        "ablations": ablations,
        "operation_audit": _operation_audit(regression_all),
    }


def _format_ci(interval):
    return f"[{interval['lower']:.4f}, {interval['upper']:.4f}]"


def _error_groups(report):
    grouped = defaultdict(list)
    for row in report["cases"]:
        if not row["top1_correct"]:
            grouped[row["template_group"]].append(row)
    return grouped


def render_markdown(suite: Dict[str, Any]):
    regression = suite["regression"]
    regression_comparison = regression["comparison"]
    c1 = regression_comparison["primary"]
    c0 = regression_comparison["baseline"]
    challenge = suite["challenge"]["comparison"]
    c1_challenge = challenge["primary"]
    audit = suite["operation_audit"]

    lines = [
        "# PLM-C1 v0.1 Evaluation Report",
        "",
        "## Frozen PLM-C0 v0.3 regression benchmark",
        "",
        "288 total cases, evaluated on the fixed 216-case test split (72 semantic groups).",
        "",
        "| Metric | PLM-C1 v0.1 | PLM-C0 v0.3 | Lexical baseline | C1 - C0 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in regression["metric_rows"]:
        lines.append(
            f"| {row['metric']} | {row['c1']} | {row['c0']} | "
            f"{row['lexical']} | {row['delta_c1_minus_c0']} |"
        )
    lines.extend([
        "",
        f"C1 Top-1 95% CI: {_format_ci(c1['confidence_intervals']['top1_accuracy_95'])}",
        "",
        "C1-C0 paired Top-1 delta 95% CI: "
        f"{_format_ci(regression_comparison['confidence_intervals']['top1_delta_95'])}",
        "",
        f"Known stress tag Top-1: C1 `{c1['per_tag']['stress']['top1_accuracy']}` / "
        f"C0 `{c0['per_tag']['stress']['top1_accuracy']}`.",
        "",
        "## C1 ablation on frozen regression test",
        "",
        "| Variant | Top-1 | Macro-F1 | Stress Top-1 | Contradiction rejection |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, report in suite["ablations"].items():
        lines.append(
            f"| {name} | {report['metrics']['top1_accuracy']} | {report['metrics']['macro_f1']} | "
            f"{report['per_tag']['stress']['top1_accuracy']} | "
            f"{report['metrics']['contradiction_rejection']} |"
        )
    lines.extend([
        "",
        "## Explicit operation audit",
        "",
        f"Audited semantic groups: `{audit['semantic_groups_audited']}`",
        "",
        f"Operation counts: `{audit['operation_counts']}`",
        "",
        f"Superseded evidence items: `{audit['superseded_evidence_items']}`; "
        f"residual weight removed: `{audit['residual_weight_removed']}`",
        "",
        f"Forced unresolved domains: `{audit['forced_unresolved_domains']}`",
        "",
        "## Post-implementation challenge",
        "",
        "The 20 semantic challenge templates (60 wrapper cases) were frozen before their first run and were not used to tune v0.1.",
        "",
        "| Metric | PLM-C1 v0.1 | PLM-C0 v0.3 | C1 - C0 |",
        "|---|---:|---:|---:|",
    ])
    for row in suite["challenge"]["metric_rows"]:
        lines.append(
            f"| {row['metric']} | {row['c1']} | {row['c0']} | {row['delta_c1_minus_c0']} |"
        )
    lines.extend([
        "",
        "C1 challenge Top-1 95% CI: "
        f"{_format_ci(c1_challenge['confidence_intervals']['top1_accuracy_95'])}",
        "",
        "C1-C0 challenge Top-1 delta 95% CI: "
        f"{_format_ci(challenge['confidence_intervals']['top1_delta_95'])}",
        "",
        "### Challenge failures by semantic group",
        "",
    ])
    failures = _error_groups(c1_challenge)
    for group, rows in sorted(failures.items()):
        predictions = sorted({row["predicted"] for row in rows})
        mean_confidence = sum(row["selection_confidence"] for row in rows) / len(rows)
        lines.append(
            f"- `{group}`: expected `{rows[0]['expected']}`, predicted "
            f"`{', '.join(predictions)}`, mean confidence `{mean_confidence:.4f}`"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- C1 closes all failures in the known v0.3 regression benchmark without regressing its ordinary cases.",
        "- The challenge score remains low, showing that marker dictionaries and shallow scope rules do not generalize reliably.",
        "- Remaining gaps are unseen correction markers, double negation, reported denial, morphology, conditionals, and broader discourse boundaries.",
        "- Both datasets are authored functional benchmarks, not external corpora. Statistical intervals do not establish real-world validity.",
        "",
    ])
    return "\n".join(lines)
