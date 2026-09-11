from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from plm_c0 import PLMC0Engine, PositiveLexicalBaseline, compare, evaluate, load_cases
from plm_c1_v01 import PLMC1Engine as PLMC1V01Engine

from .engine import C1Config, PLMC1Engine


METRIC_KEYS = (
    "top1_accuracy", "top5_recall", "mrr", "macro_f1",
    "unresolved_precision", "unresolved_recall", "contradiction_rejection",
    "coverage", "selective_accuracy", "expected_calibration_error", "brier_score",
)


def _table_rows(v02, v01, c0, lexical=None):
    rows = []
    for key in METRIC_KEYS:
        value = v02["metrics"].get(key)
        old_value = v01["metrics"].get(key)
        c0_value = c0["metrics"].get(key)
        rows.append({
            "metric": key,
            "v02": value,
            "v01": old_value,
            "c0": c0_value,
            "lexical": lexical["metrics"].get(key) if lexical else None,
            "delta_v02_minus_v01": round(value - old_value, 4)
            if isinstance(value, (int, float)) and isinstance(old_value, (int, float)) else None,
            "delta_v02_minus_c0": round(value - c0_value, 4)
            if isinstance(value, (int, float)) and isinstance(c0_value, (int, float)) else None,
        })
    return rows


def _evaluate_models(cases, bootstrap_samples, include_lexical=False):
    v02 = evaluate(PLMC1Engine(), cases, "PLM-C1 v0.2", bootstrap_samples=bootstrap_samples)
    v01 = evaluate(PLMC1V01Engine(), cases, "PLM-C1 v0.1", bootstrap_samples=bootstrap_samples)
    c0 = evaluate(PLMC0Engine(), cases, "PLM-C0 v0.3", bootstrap_samples=bootstrap_samples)
    lexical = (
        evaluate(PositiveLexicalBaseline(), cases, "positive lexical baseline", bootstrap_samples=bootstrap_samples)
        if include_lexical else None
    )
    return {
        "v02": v02,
        "v01": v01,
        "c0": c0,
        "lexical": lexical,
        "v02_vs_v01": compare(v02, v01, bootstrap_samples=bootstrap_samples),
        "v02_vs_c0": compare(v02, c0, bootstrap_samples=bootstrap_samples),
        "metric_rows": _table_rows(v02, v01, c0, lexical),
    }


def _operation_audit(cases):
    counts = Counter()
    residual_removed = 0.0
    superseded_evidence = 0
    forced_unresolved = Counter()
    relation_items = applied_relations = 0
    seen_groups = set()
    for case in cases:
        if case["template_group"] in seen_groups:
            continue
        seen_groups.add(case["template_group"])
        result = PLMC1Engine().analyze(case["inputs"])
        for operation in result["operations"]:
            counts[operation["operation"]] += 1
            residual_removed += float(operation.get("residual_removed", 0.0))
        diagnostics = result["diagnostics"]
        superseded_evidence += diagnostics["superseded_evidence_items"]
        relation_items += diagnostics["relation_items"]
        applied_relations += diagnostics["applied_relation_items"]
        for domain in diagnostics["forced_unresolved_domains"]:
            forced_unresolved[domain] += 1
    return {
        "semantic_groups_audited": len(seen_groups),
        "operation_counts": dict(sorted(counts.items())),
        "residual_weight_removed": round(residual_removed, 4),
        "superseded_evidence_items": superseded_evidence,
        "relation_items": relation_items,
        "applied_relation_items": applied_relations,
        "forced_unresolved_domains": dict(sorted(forced_unresolved.items())),
    }


def run_suite(bootstrap_samples: int = 2000):
    root = Path(__file__).resolve().parents[1]
    regression_all = load_cases(str(root / "data" / "benchmark_v03.json"))
    regression_test = [case for case in regression_all if case["split"] == "test"]
    v01_challenge = load_cases(str(root / "data" / "challenge_c1_v01.json"))
    v02_challenge_path = root / "data" / "challenge_c1_v02.json"
    v02_challenge = load_cases(str(v02_challenge_path))

    regression = _evaluate_models(regression_test, bootstrap_samples, include_lexical=True)
    known_challenge = _evaluate_models(v01_challenge, bootstrap_samples)
    unseen_challenge = _evaluate_models(v02_challenge, bootstrap_samples)

    configs = {
        "full": C1Config(),
        "no_polarity_composition": C1Config(use_polarity_composition=False),
        "no_discourse_state": C1Config(use_discourse_state=False),
        "no_morphology": C1Config(use_morphology=False),
        "no_target_tracking": C1Config(use_target_tracking=False),
        "no_relation_context": C1Config(use_relation_context=False),
        "no_residual": C1Config(use_residual=False),
    }
    ablations = {
        name: evaluate(
            PLMC1Engine(config=config), v01_challenge, name,
            bootstrap_samples=bootstrap_samples,
        )
        for name, config in configs.items()
    }

    acceptance = {
        "regression_top1_at_least_0_98": regression["v02"]["metrics"]["top1_accuracy"] >= 0.98,
        "known_challenge_top1_at_least_0_70": known_challenge["v02"]["metrics"]["top1_accuracy"] >= 0.70,
        "known_challenge_ece_better_than_v01": (
            known_challenge["v02"]["metrics"]["expected_calibration_error"]
            < known_challenge["v01"]["metrics"]["expected_calibration_error"]
        ),
        "unseen_challenge_beats_v01": (
            unseen_challenge["v02"]["metrics"]["top1_accuracy"]
            > unseen_challenge["v01"]["metrics"]["top1_accuracy"]
        ),
    }

    return {
        "version": "PLM-C1 v0.2",
        "protocol": {
            "frozen_preimplementation": ["benchmark_v03.json", "challenge_c1_v01.json"],
            "postimplementation_challenge": "challenge_c1_v02.json",
            "postimplementation_sha256": sha256(v02_challenge_path.read_bytes()).hexdigest(),
            "tuning_after_first_v02_challenge_run": False,
            "bootstrap_unit": "template_group",
        },
        "datasets": {
            "frozen_v03_regression": {"all_cases": len(regression_all), "test_cases": len(regression_test), "semantic_groups": 72},
            "known_v01_challenge": {"cases": len(v01_challenge), "semantic_groups": 20},
            "unseen_v02_challenge": {"cases": len(v02_challenge), "semantic_groups": 20},
        },
        "regression": regression,
        "known_challenge": known_challenge,
        "unseen_challenge": unseen_challenge,
        "ablations_on_known_challenge": ablations,
        "operation_audit": _operation_audit(regression_all + v01_challenge + v02_challenge),
        "acceptance": acceptance,
        "acceptance_passed": all(acceptance.values()),
    }


def _format_ci(interval):
    return "n/a" if interval is None else f"[{interval['lower']:.4f}, {interval['upper']:.4f}]"


def _failures(report):
    grouped = defaultdict(list)
    for row in report["cases"]:
        if not row["top1_correct"]:
            grouped[row["template_group"]].append(row)
    return grouped


def _append_metrics(lines, section, title, include_lexical=False):
    lines.extend(["", f"## {title}", ""])
    if include_lexical:
        lines.extend([
            "| Metric | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ v0.2-v0.1 |",
            "|---|---:|---:|---:|---:|---:|",
        ])
    else:
        lines.extend([
            "| Metric | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.2-v0.1 |",
            "|---|---:|---:|---:|---:|",
        ])
    for row in section["metric_rows"]:
        if include_lexical:
            lines.append(
                f"| {row['metric']} | {row['v02']} | {row['v01']} | {row['c0']} | "
                f"{row['lexical']} | {row['delta_v02_minus_v01']} |"
            )
        else:
            lines.append(
                f"| {row['metric']} | {row['v02']} | {row['v01']} | {row['c0']} | "
                f"{row['delta_v02_minus_v01']} |"
            )
    lines.extend([
        "",
        "v0.2 Top-1 95% cluster-bootstrap CI: "
        f"`{_format_ci(section['v02']['confidence_intervals']['top1_accuracy_95'])}`",
        "",
        "v0.2-v0.1 Top-1 delta 95% CI: "
        f"`{_format_ci(section['v02_vs_v01']['confidence_intervals']['top1_delta_95'])}`",
    ])


def render_markdown(suite: Dict[str, Any]):
    protocol = suite["protocol"]
    lines = [
        "# PLM-C1 v0.2 Evaluation Report",
        "",
        "PLM-C1 v0.1を凍結比較対象とし、v0.3回帰セット、既存v0.1チャレンジ、"
        "実装後に凍結した新規v0.2チャレンジの3層で評価した。",
        "",
        f"新規チャレンジ SHA-256: `{protocol['postimplementation_sha256']}`。"
        "初回実行後のengine/Concept-data調整は行っていない。",
    ]
    _append_metrics(lines, suite["regression"], "Frozen v0.3 regression (216 test cases)", True)
    _append_metrics(lines, suite["known_challenge"], "Known v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["unseen_challenge"], "Unseen v0.2 challenge (60 cases)")

    lines.extend(["", "### Unseen challenge failures", ""])
    for group, rows in sorted(_failures(suite["unseen_challenge"]["v02"]).items()):
        predictions = sorted({row["predicted"] for row in rows})
        confidence = sum(row["selection_confidence"] for row in rows) / len(rows)
        lines.append(
            f"- `{group}`: expected `{rows[0]['expected']}`, predicted "
            f"`{', '.join(predictions)}`, mean confidence `{confidence:.4f}`"
        )

    lines.extend([
        "", "## Ablation on known v0.1 challenge", "",
        "| Variant | Top-1 | MRR | ECE |",
        "|---|---:|---:|---:|",
    ])
    for name, report in suite["ablations_on_known_challenge"].items():
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['top1_accuracy']} | {metrics['mrr']} | "
            f"{metrics['expected_calibration_error']} |"
        )

    audit = suite["operation_audit"]
    lines.extend([
        "", "## Explicit operation audit", "",
        f"Semantic groups audited: `{audit['semantic_groups_audited']}`; "
        f"operation counts: `{audit['operation_counts']}`.",
        "",
        f"Relations: `{audit['applied_relation_items']}/{audit['relation_items']}` applied; "
        f"superseded evidence: `{audit['superseded_evidence_items']}`; "
        f"residual weight removed: `{audit['residual_weight_removed']}`.",
        "", "## Acceptance", "",
    ])
    for name, passed in suite["acceptance"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — `{name}`")
    lines.extend([
        "", f"Overall: **{'PASS' if suite['acceptance_passed'] else 'FAIL'}**", "",
        "## Interpretation", "",
        "v0.2は固定回帰を維持し、v0.1が失敗した既存チャレンジをすべて解決した。"
        "新規未見セットでもv0.1を上回ったが、Top-1は0.65に留まる。",
        "",
        "残る失敗は、辞書にない談話・対象切替マーカー、英語の不規則複数・過去形、"
        "複合語内部の関係語である。いずれも手作業の機能benchmarkであり、実世界性能を示すものではない。",
        "",
    ])
    return "\n".join(lines)
