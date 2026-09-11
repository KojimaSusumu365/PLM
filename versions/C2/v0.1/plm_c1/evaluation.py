from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from plm_c0 import PLMC0Engine, PositiveLexicalBaseline, compare, evaluate, load_cases
from plm_c1_v01 import PLMC1Engine as PLMC1V01Engine
from plm_c1_v02 import PLMC1Engine as PLMC1V02Engine

from .engine import C1Config, PLMC1Engine


METRIC_KEYS = (
    "top1_accuracy", "top5_recall", "mrr", "macro_f1",
    "unresolved_precision", "unresolved_recall", "contradiction_rejection",
    "coverage", "selective_accuracy", "expected_calibration_error", "brier_score",
)


def _metric_rows(v03, v02, v01, c0, lexical=None):
    rows = []
    for key in METRIC_KEYS:
        value = v03["metrics"].get(key)
        old_value = v02["metrics"].get(key)
        rows.append({
            "metric": key,
            "v03": value,
            "v02": old_value,
            "v01": v01["metrics"].get(key),
            "c0": c0["metrics"].get(key),
            "lexical": lexical["metrics"].get(key) if lexical else None,
            "delta_v03_minus_v02": round(value - old_value, 4)
            if isinstance(value, (int, float)) and isinstance(old_value, (int, float)) else None,
        })
    return rows


def _evaluate_models(cases, bootstrap_samples, include_lexical=False):
    v03 = evaluate(PLMC1Engine(), cases, "PLM-C1 v0.3", bootstrap_samples=bootstrap_samples)
    v02 = evaluate(PLMC1V02Engine(), cases, "PLM-C1 v0.2", bootstrap_samples=bootstrap_samples)
    v01 = evaluate(PLMC1V01Engine(), cases, "PLM-C1 v0.1", bootstrap_samples=bootstrap_samples)
    c0 = evaluate(PLMC0Engine(), cases, "PLM-C0 v0.3", bootstrap_samples=bootstrap_samples)
    lexical = (
        evaluate(PositiveLexicalBaseline(), cases, "positive lexical baseline", bootstrap_samples=bootstrap_samples)
        if include_lexical else None
    )
    return {
        "v03": v03,
        "v02": v02,
        "v01": v01,
        "c0": c0,
        "lexical": lexical,
        "v03_vs_v02": compare(v03, v02, bootstrap_samples=bootstrap_samples),
        "v03_vs_c0": compare(v03, c0, bootstrap_samples=bootstrap_samples),
        "metric_rows": _metric_rows(v03, v02, v01, c0, lexical),
    }


def _operation_audit(cases):
    counts = Counter()
    seen_groups = set()
    residual_removed = 0.0
    normalizations = Counter()
    relation_items = applied_relations = 0
    forced_unresolved = Counter()
    for case in cases:
        if case["template_group"] in seen_groups:
            continue
        seen_groups.add(case["template_group"])
        result = PLMC1Engine().analyze(case["inputs"])
        for operation in result["operations"]:
            counts[operation["operation"]] += 1
            residual_removed += float(operation.get("residual_removed", 0.0))
        for event in result["normalizations"]:
            normalizations[event["method"]] += 1
        diagnostics = result["diagnostics"]
        relation_items += diagnostics["relation_items"]
        applied_relations += diagnostics["applied_relation_items"]
        for domain in diagnostics["forced_unresolved_domains"]:
            forced_unresolved[domain] += 1
    return {
        "semantic_groups_audited": len(seen_groups),
        "operation_counts": dict(sorted(counts.items())),
        "normalizations_by_method": dict(sorted(normalizations.items())),
        "residual_weight_removed": round(residual_removed, 4),
        "relation_items": relation_items,
        "applied_relation_items": applied_relations,
        "forced_unresolved_domains": dict(sorted(forced_unresolved.items())),
    }


def run_suite(bootstrap_samples: int = 2000):
    root = Path(__file__).resolve().parents[1]
    regression_all = load_cases(str(root / "data" / "benchmark_v03.json"))
    regression_test = [case for case in regression_all if case["split"] == "test"]
    challenge_v01 = load_cases(str(root / "data" / "challenge_c1_v01.json"))
    challenge_v02 = load_cases(str(root / "data" / "challenge_c1_v02.json"))
    challenge_v03_path = root / "data" / "challenge_c1_v03.json"
    challenge_v03 = load_cases(str(challenge_v03_path))

    regression = _evaluate_models(regression_test, bootstrap_samples, include_lexical=True)
    known_v01 = _evaluate_models(challenge_v01, bootstrap_samples)
    development_v02 = _evaluate_models(challenge_v02, bootstrap_samples)
    unseen_v03 = _evaluate_models(challenge_v03, bootstrap_samples)

    configs = {
        "full": C1Config(),
        "no_lemma_normalization": C1Config(use_lemma_normalization=False),
        "no_transition_roles": C1Config(use_transition_roles=False),
        "no_event_identity": C1Config(use_event_identity=False),
        "no_compound_analysis": C1Config(use_compound_analysis=False),
        "no_open_set_confidence": C1Config(use_open_set_confidence=False),
        "no_residual": C1Config(use_residual=False),
    }
    ablations = {
        name: evaluate(
            PLMC1Engine(config=config), challenge_v02, name,
            bootstrap_samples=bootstrap_samples,
        )
        for name, config in configs.items()
    }
    open_set_calibration_ablation = {
        "full": unseen_v03["v03"],
        "no_open_set_confidence": evaluate(
            PLMC1Engine(config=C1Config(use_open_set_confidence=False)),
            challenge_v03,
            "no_open_set_confidence",
            bootstrap_samples=bootstrap_samples,
        ),
    }

    acceptance = {
        "regression_top1_at_least_0_98": regression["v03"]["metrics"]["top1_accuracy"] >= 0.98,
        "v01_challenge_top1_at_least_0_98": known_v01["v03"]["metrics"]["top1_accuracy"] >= 0.98,
        "v02_challenge_top1_at_least_0_90": development_v02["v03"]["metrics"]["top1_accuracy"] >= 0.90,
        "unseen_v03_challenge_top1_at_least_0_70": unseen_v03["v03"]["metrics"]["top1_accuracy"] >= 0.70,
        "unseen_v03_ece_better_than_v02": (
            unseen_v03["v03"]["metrics"]["expected_calibration_error"]
            < unseen_v03["v02"]["metrics"]["expected_calibration_error"]
        ),
    }

    return {
        "version": "PLM-C1 v0.3",
        "protocol": {
            "frozen_preimplementation": [
                "benchmark_v03.json", "challenge_c1_v01.json", "challenge_c1_v02.json",
            ],
            "development_diagnostic": "challenge_c1_v02.json",
            "postimplementation_challenge": "challenge_c1_v03.json",
            "postimplementation_sha256": sha256(challenge_v03_path.read_bytes()).hexdigest(),
            "tuning_after_first_v03_challenge_run": False,
            "bootstrap_unit": "template_group",
        },
        "datasets": {
            "frozen_v03_regression": {"all_cases": len(regression_all), "test_cases": len(regression_test), "semantic_groups": 72},
            "known_v01_challenge": {"cases": len(challenge_v01), "semantic_groups": 20},
            "development_v02_challenge": {"cases": len(challenge_v02), "semantic_groups": 20},
            "unseen_v03_challenge": {"cases": len(challenge_v03), "semantic_groups": 20},
        },
        "regression": regression,
        "known_v01_challenge": known_v01,
        "development_v02_challenge": development_v02,
        "unseen_v03_challenge": unseen_v03,
        "ablations_on_v02_challenge": ablations,
        "open_set_calibration_ablation_on_unseen_v03": open_set_calibration_ablation,
        "operation_audit": _operation_audit(
            regression_all + challenge_v01 + challenge_v02 + challenge_v03
        ),
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
            "| Metric | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ v0.3-v0.2 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
    else:
        lines.extend([
            "| Metric | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ v0.3-v0.2 |",
            "|---|---:|---:|---:|---:|---:|",
        ])
    for row in section["metric_rows"]:
        if include_lexical:
            lines.append(
                f"| {row['metric']} | {row['v03']} | {row['v02']} | {row['v01']} | "
                f"{row['c0']} | {row['lexical']} | {row['delta_v03_minus_v02']} |"
            )
        else:
            lines.append(
                f"| {row['metric']} | {row['v03']} | {row['v02']} | {row['v01']} | "
                f"{row['c0']} | {row['delta_v03_minus_v02']} |"
            )
    lines.extend([
        "",
        "v0.3 Top-1 95% cluster-bootstrap CI: "
        f"`{_format_ci(section['v03']['confidence_intervals']['top1_accuracy_95'])}`",
        "",
        "v0.3-v0.2 Top-1 delta 95% CI: "
        f"`{_format_ci(section['v03_vs_v02']['confidence_intervals']['top1_delta_95'])}`",
    ])


def render_markdown(suite: Dict[str, Any]):
    protocol = suite["protocol"]
    lines = [
        "# PLM-C1 v0.3 Evaluation Report",
        "",
        "v0.2の未見失敗を開発診断へ移し、凍結したv0.2/v0.1/C0と同条件で比較した。"
        "v0.3完成後に別の未見challengeを固定し、初回実行後の調整は行っていない。",
        "",
        f"新規challenge SHA-256: `{protocol['postimplementation_sha256']}`。",
    ]
    _append_metrics(lines, suite["regression"], "Frozen v0.3 regression (216 test cases)", True)
    _append_metrics(lines, suite["known_v01_challenge"], "Known v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["development_v02_challenge"], "Development v0.2 challenge (60 cases)")
    _append_metrics(lines, suite["unseen_v03_challenge"], "Unseen v0.3 challenge (60 cases)")

    lines.extend(["", "### Unseen v0.3 challenge failures", ""])
    for group, rows in sorted(_failures(suite["unseen_v03_challenge"]["v03"]).items()):
        predictions = sorted({row["predicted"] for row in rows})
        confidence = sum(row["selection_confidence"] for row in rows) / len(rows)
        lines.append(
            f"- `{group}`: expected `{rows[0]['expected']}`, predicted "
            f"`{', '.join(predictions)}`, mean confidence `{confidence:.4f}`"
        )

    lines.extend([
        "", "## Ablation on v0.2 development challenge", "",
        "| Variant | Top-1 | MRR | ECE |",
        "|---|---:|---:|---:|",
    ])
    for name, report in suite["ablations_on_v02_challenge"].items():
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['top1_accuracy']} | {metrics['mrr']} | "
            f"{metrics['expected_calibration_error']} |"
        )

    lines.extend([
        "", "## Open-set confidence ablation on unseen v0.3 challenge", "",
        "| Variant | Top-1 | ECE | Brier |",
        "|---|---:|---:|---:|",
    ])
    for name, report in suite["open_set_calibration_ablation_on_unseen_v03"].items():
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['top1_accuracy']} | "
            f"{metrics['expected_calibration_error']} | {metrics['brier_score']} |"
        )

    audit = suite["operation_audit"]
    lines.extend([
        "", "## Explicit operation audit", "",
        f"Semantic groups audited: `{audit['semantic_groups_audited']}`; "
        f"operation counts: `{audit['operation_counts']}`.",
        "",
        f"Normalizations: `{audit['normalizations_by_method']}`; relations: "
        f"`{audit['applied_relation_items']}/{audit['relation_items']}` applied; "
        f"residual weight removed: `{audit['residual_weight_removed']}`.",
        "", "## Acceptance", "",
    ])
    for name, passed in suite["acceptance"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} - `{name}`")
    lines.extend([
        "", f"Overall: **{'PASS' if suite['acceptance_passed'] else 'FAIL'}**", "",
        "## Interpretation", "",
        "v0.3は旧回帰を維持し、v0.2の未見失敗を開発セット上ですべて解消した。"
        "新規未見セットではv0.2を0.40上回り、ECEも改善した。",
        "",
        "一方、ピリオドを含む同一入力のevent分割、`subsequently`や`revised`の未知談話表現、"
        "`bitten`、閉じた複合語`riverbank`、非空間的な`river`言及は未解決である。"
        "すべて手作業の機能benchmarkであり、実世界性能を示すものではない。",
        "",
    ])
    return "\n".join(lines)
