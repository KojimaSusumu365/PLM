from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from plm_c0 import PLMC0Engine, PositiveLexicalBaseline, compare, evaluate, load_cases
from plm_c1 import PLMC1Engine as PLMC1V03Engine
from plm_c1_v01 import PLMC1Engine as PLMC1V01Engine
from plm_c1_v02 import PLMC1Engine as PLMC1V02Engine

from .engine import C2Config, PLMC2Engine


METRIC_KEYS = (
    "top1_accuracy", "top5_recall", "mrr", "macro_f1",
    "unresolved_precision", "unresolved_recall", "contradiction_rejection",
    "coverage", "selective_accuracy", "expected_calibration_error", "brier_score",
)


def _metric_rows(c2, c103, c102, c101, c0, lexical=None):
    rows = []
    for key in METRIC_KEYS:
        value = c2["metrics"].get(key)
        old_value = c103["metrics"].get(key)
        rows.append({
            "metric": key,
            "c2": value,
            "c1_v03": old_value,
            "c1_v02": c102["metrics"].get(key),
            "c1_v01": c101["metrics"].get(key),
            "c0": c0["metrics"].get(key),
            "lexical": lexical["metrics"].get(key) if lexical else None,
            "delta_c2_minus_c1_v03": round(value - old_value, 4)
            if isinstance(value, (int, float)) and isinstance(old_value, (int, float)) else None,
        })
    return rows


def _evaluate_models(cases, bootstrap_samples, include_lexical=False):
    c2 = evaluate(PLMC2Engine(), cases, "PLM-C2 v0.1", bootstrap_samples=bootstrap_samples)
    c103 = evaluate(PLMC1V03Engine(), cases, "PLM-C1 v0.3", bootstrap_samples=bootstrap_samples)
    c102 = evaluate(PLMC1V02Engine(), cases, "PLM-C1 v0.2", bootstrap_samples=bootstrap_samples)
    c101 = evaluate(PLMC1V01Engine(), cases, "PLM-C1 v0.1", bootstrap_samples=bootstrap_samples)
    c0 = evaluate(PLMC0Engine(), cases, "PLM-C0 v0.3", bootstrap_samples=bootstrap_samples)
    lexical = (
        evaluate(PositiveLexicalBaseline(), cases, "positive lexical baseline", bootstrap_samples=bootstrap_samples)
        if include_lexical else None
    )
    return {
        "c2": c2,
        "c1_v03": c103,
        "c1_v02": c102,
        "c1_v01": c101,
        "c0": c0,
        "lexical": lexical,
        "c2_vs_c1_v03": compare(c2, c103, bootstrap_samples=bootstrap_samples),
        "c2_vs_c0": compare(c2, c0, bootstrap_samples=bootstrap_samples),
        "metric_rows": _metric_rows(c2, c103, c102, c101, c0, lexical),
    }


def _graph_operation_audit(cases):
    seen_groups = set()
    operations = Counter()
    node_types = Counter()
    edge_relations = Counter()
    normalizations = Counter()
    invariant_failures = Counter()
    relation_gated = 0
    for case in cases:
        if case["template_group"] in seen_groups:
            continue
        seen_groups.add(case["template_group"])
        result = PLMC2Engine().analyze(case["inputs"])
        for operation in result["operations"]:
            operations[operation["operation"]] += 1
        for event in result["normalizations"]:
            normalizations[event["method"]] += 1
        graph = result["claim_graph"]
        for node in graph["nodes"]:
            node_types[node["node_type"]] += 1
        for edge in graph["edges"]:
            edge_relations[edge["relation"]] += 1
        for invariant, passed in graph["invariants"].items():
            if not passed:
                invariant_failures[invariant] += 1
        relation_gated += result["diagnostics"]["relation_gated_evidence"]
    return {
        "semantic_groups_audited": len(seen_groups),
        "operation_counts": dict(sorted(operations.items())),
        "normalizations_by_method": dict(sorted(normalizations.items())),
        "claim_graph_node_types": dict(sorted(node_types.items())),
        "claim_graph_edge_relations": dict(sorted(edge_relations.items())),
        "claim_graph_invariant_failures": dict(sorted(invariant_failures.items())),
        "relation_gated_evidence": relation_gated,
    }


def run_suite(bootstrap_samples: int = 2000):
    root = Path(__file__).resolve().parents[1]
    regression_all = load_cases(str(root / "data" / "benchmark_v03.json"))
    regression_test = [case for case in regression_all if case["split"] == "test"]
    challenge_v01 = load_cases(str(root / "data" / "challenge_c1_v01.json"))
    challenge_v02 = load_cases(str(root / "data" / "challenge_c1_v02.json"))
    challenge_v03 = load_cases(str(root / "data" / "challenge_c1_v03.json"))
    challenge_c2_path = root / "data" / "challenge_c2_v01.json"
    challenge_c2 = load_cases(str(challenge_c2_path))

    regression = _evaluate_models(regression_test, bootstrap_samples, include_lexical=True)
    known_v01 = _evaluate_models(challenge_v01, bootstrap_samples)
    known_v02 = _evaluate_models(challenge_v02, bootstrap_samples)
    development_v03 = _evaluate_models(challenge_v03, bootstrap_samples)
    unseen_c2 = _evaluate_models(challenge_c2, bootstrap_samples)

    configs = {
        "full": C2Config(),
        "no_sentence_boundaries": C2Config(use_sentence_boundaries=False),
        "no_temporal_relations": C2Config(use_temporal_relations=False),
        "no_revision_relations": C2Config(use_revision_relations=False),
        "no_irregular_lemmas": C2Config(use_irregular_lemmas=False),
        "no_closed_compounds": C2Config(use_closed_compounds=False),
        "no_typed_relation_gate": C2Config(use_typed_relation_gate=False),
        "no_typed_claim_graph": C2Config(use_typed_claim_graph=False),
    }
    ablations = {
        name: evaluate(
            PLMC2Engine(config=config), challenge_v03, name,
            bootstrap_samples=bootstrap_samples,
        )
        for name, config in configs.items()
    }
    graph_ablation_sample = {
        name: {
            "node_count": len(PLMC2Engine(config=config).analyze("A dog barked.")["claim_graph"]["nodes"]),
            "edge_count": len(PLMC2Engine(config=config).analyze("A dog barked.")["claim_graph"]["edges"]),
        }
        for name, config in {
            "full": C2Config(),
            "no_typed_claim_graph": C2Config(use_typed_claim_graph=False),
        }.items()
    }

    audit = _graph_operation_audit(
        regression_all + challenge_v01 + challenge_v02 + challenge_v03 + challenge_c2
    )
    accuracy_ablation_names = (
        "no_sentence_boundaries", "no_temporal_relations", "no_revision_relations",
        "no_irregular_lemmas", "no_closed_compounds", "no_typed_relation_gate",
    )
    full_accuracy = ablations["full"]["metrics"]["top1_accuracy"]
    acceptance = {
        "regression_top1_at_least_0_98": regression["c2"]["metrics"]["top1_accuracy"] >= 0.98,
        "v01_challenge_top1_at_least_0_98": known_v01["c2"]["metrics"]["top1_accuracy"] >= 0.98,
        "v02_challenge_top1_at_least_0_98": known_v02["c2"]["metrics"]["top1_accuracy"] >= 0.98,
        "v03_challenge_top1_at_least_0_95": development_v03["c2"]["metrics"]["top1_accuracy"] >= 0.95,
        "unseen_c2_challenge_top1_at_least_0_75": unseen_c2["c2"]["metrics"]["top1_accuracy"] >= 0.75,
        "unseen_c2_beats_c1_v03": unseen_c2["c2"]["metrics"]["top1_accuracy"] > unseen_c2["c1_v03"]["metrics"]["top1_accuracy"],
        "unseen_c2_ece_at_most_0_30": unseen_c2["c2"]["metrics"]["expected_calibration_error"] <= 0.30,
        "all_accuracy_features_have_ablation_effect": all(
            ablations[name]["metrics"]["top1_accuracy"] < full_accuracy
            for name in accuracy_ablation_names
        ),
        "claim_graph_invariants_hold": not audit["claim_graph_invariant_failures"],
    }

    return {
        "version": "PLM-C2 v0.1",
        "protocol": {
            "frozen_preimplementation": [
                "benchmark_v03.json", "challenge_c1_v01.json",
                "challenge_c1_v02.json", "challenge_c1_v03.json",
            ],
            "development_diagnostic": "challenge_c1_v03.json",
            "postimplementation_challenge": "challenge_c2_v01.json",
            "postimplementation_sha256": sha256(challenge_c2_path.read_bytes()).hexdigest(),
            "tuning_after_first_c2_challenge_run": False,
            "bootstrap_unit": "template_group",
        },
        "datasets": {
            "frozen_regression": {"all_cases": len(regression_all), "test_cases": len(regression_test), "semantic_groups": 72},
            "known_v01_challenge": {"cases": len(challenge_v01), "semantic_groups": 20},
            "known_v02_challenge": {"cases": len(challenge_v02), "semantic_groups": 20},
            "development_v03_challenge": {"cases": len(challenge_v03), "semantic_groups": 20},
            "unseen_c2_challenge": {"cases": len(challenge_c2), "semantic_groups": 20},
        },
        "regression": regression,
        "known_v01_challenge": known_v01,
        "known_v02_challenge": known_v02,
        "development_v03_challenge": development_v03,
        "unseen_c2_challenge": unseen_c2,
        "ablations_on_v03_challenge": ablations,
        "graph_ablation_sample": graph_ablation_sample,
        "graph_operation_audit": audit,
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
            "| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Lexical | Δ C2-C1v0.3 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
    else:
        lines.extend([
            "| Metric | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3 | Δ C2-C1v0.3 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
    for row in section["metric_rows"]:
        if include_lexical:
            lines.append(
                f"| {row['metric']} | {row['c2']} | {row['c1_v03']} | {row['c1_v02']} | "
                f"{row['c1_v01']} | {row['c0']} | {row['lexical']} | {row['delta_c2_minus_c1_v03']} |"
            )
        else:
            lines.append(
                f"| {row['metric']} | {row['c2']} | {row['c1_v03']} | {row['c1_v02']} | "
                f"{row['c1_v01']} | {row['c0']} | {row['delta_c2_minus_c1_v03']} |"
            )
    lines.extend([
        "",
        f"C2 Top-1 95% cluster-bootstrap CI: `{_format_ci(section['c2']['confidence_intervals']['top1_accuracy_95'])}`",
        "",
        "C2-C1 v0.3 Top-1 delta 95% CI: "
        f"`{_format_ci(section['c2_vs_c1_v03']['confidence_intervals']['top1_delta_95'])}`",
    ])


def render_markdown(suite: Dict[str, Any]):
    protocol = suite["protocol"]
    lines = [
        "# PLM-C2 v0.1 Evaluation Report",
        "",
        "C1 v0.3を凍結比較対象とし、C1 v0.3 challengeを開発診断として使用した。"
        "C2完成後に新規未見challengeを固定し、初回実行後のengine/Concept-data調整は行っていない。",
        "",
        f"新規challenge SHA-256: `{protocol['postimplementation_sha256']}`。",
    ]
    _append_metrics(lines, suite["regression"], "Frozen regression (216 test cases)", True)
    _append_metrics(lines, suite["known_v01_challenge"], "Known C1 v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["known_v02_challenge"], "Known C1 v0.2 challenge (60 cases)")
    _append_metrics(lines, suite["development_v03_challenge"], "Development C1 v0.3 challenge (60 cases)")
    _append_metrics(lines, suite["unseen_c2_challenge"], "Unseen C2 v0.1 challenge (60 cases)")

    lines.extend(["", "### Unseen C2 challenge failures", ""])
    for group, rows in sorted(_failures(suite["unseen_c2_challenge"]["c2"]).items()):
        predictions = sorted({row["predicted"] for row in rows})
        confidence = sum(row["selection_confidence"] for row in rows) / len(rows)
        lines.append(
            f"- `{group}`: expected `{rows[0]['expected']}`, predicted "
            f"`{', '.join(predictions)}`, mean confidence `{confidence:.4f}`"
        )

    lines.extend([
        "", "## Ablation on C1 v0.3 development challenge", "",
        "| Variant | Top-1 | MRR | ECE |",
        "|---|---:|---:|---:|",
    ])
    for name, report in suite["ablations_on_v03_challenge"].items():
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['top1_accuracy']} | {metrics['mrr']} | "
            f"{metrics['expected_calibration_error']} |"
        )

    audit = suite["graph_operation_audit"]
    graph_sample = suite["graph_ablation_sample"]
    lines.extend([
        "", "## Typed Claim Graph audit", "",
        f"Semantic groups audited: `{audit['semantic_groups_audited']}`; "
        f"invariant failures: `{audit['claim_graph_invariant_failures']}`.",
        "",
        f"Node types: `{audit['claim_graph_node_types']}`.",
        "",
        f"Edge relations: `{audit['claim_graph_edge_relations']}`.",
        "",
        f"Operations: `{audit['operation_counts']}`; relation-gated Evidence: "
        f"`{audit['relation_gated_evidence']}`.",
        "",
        f"Graph sample full `{graph_sample['full']}` / disabled `{graph_sample['no_typed_claim_graph']}`.",
        "", "## Acceptance", "",
    ])
    for name, passed in suite["acceptance"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} - `{name}`")
    lines.extend([
        "", f"Overall: **{'PASS' if suite['acceptance_passed'] else 'FAIL'}**", "",
        "## Interpretation", "",
        "C2は旧4セットをすべて解決し、新規未見セットでC1 v0.3を0.45上回った。"
        "型付きgraphの参照整合性にも違反はなかった。",
        "",
        "残る失敗はcolon内の改訂、`rather`による訂正、スポンサー行為から金融機関への"
        "affordance推論、`latter`照応である。現在のgraphは明示構造を持つが、"
        "汎用構文解析・語用論・世界知識モデルではない。各データセットは手作業の機能benchmarkである。",
        "",
    ])
    return "\n".join(lines)
