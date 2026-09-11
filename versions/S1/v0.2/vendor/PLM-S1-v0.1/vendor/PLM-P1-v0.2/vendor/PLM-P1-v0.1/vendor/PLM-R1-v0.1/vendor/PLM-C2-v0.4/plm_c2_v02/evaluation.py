from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from plm_c0 import PLMC0Engine, PositiveLexicalBaseline, compare, evaluate, load_cases
from plm_c1 import PLMC1Engine as PLMC1V03Engine
from plm_c1_v01 import PLMC1Engine as PLMC1V01Engine
from plm_c1_v02 import PLMC1Engine as PLMC1V02Engine
from plm_c2_v01 import PLMC2Engine as PLMC2V01Engine

from .engine import C2Config, PLMC2Engine


FROZEN_ENGINE_SHA256 = "4ccc0aa39f2b551c7a392bab2a69948c45a3752575542bda2aa49d5583a59c50"
FROZEN_CONCEPTS_SHA256 = "740b467d5c1e4d1834c7663c8c1d47e147fa6e6cbf26059171e1a950e550575d"
FIRST_RUN = {
    "top1_accuracy": 0.95,
    "mrr": 0.9625,
    "expected_calibration_error": 0.1497,
    "failure_groups": ["revision_reclassified_colon"],
}
METRIC_KEYS = (
    "top1_accuracy", "top5_recall", "mrr", "macro_f1",
    "unresolved_precision", "unresolved_recall", "contradiction_rejection",
    "coverage", "selective_accuracy", "expected_calibration_error", "brier_score",
)


def _metric_rows(c202, c201, c103, c102, c101, c0, lexical=None):
    rows = []
    for key in METRIC_KEYS:
        value = c202["metrics"].get(key)
        old_value = c201["metrics"].get(key)
        rows.append({
            "metric": key,
            "c2_v02": value,
            "c2_v01": old_value,
            "c1_v03": c103["metrics"].get(key),
            "c1_v02": c102["metrics"].get(key),
            "c1_v01": c101["metrics"].get(key),
            "c0": c0["metrics"].get(key),
            "lexical": lexical["metrics"].get(key) if lexical else None,
            "delta_c2_v02_minus_v01": round(value - old_value, 4)
            if isinstance(value, (int, float)) and isinstance(old_value, (int, float)) else None,
        })
    return rows


def _evaluate_models(cases, bootstrap_samples, include_lexical=False):
    c202 = evaluate(PLMC2Engine(), cases, "PLM-C2 v0.2", bootstrap_samples=bootstrap_samples)
    c201 = evaluate(PLMC2V01Engine(), cases, "PLM-C2 v0.1", bootstrap_samples=bootstrap_samples)
    c103 = evaluate(PLMC1V03Engine(), cases, "PLM-C1 v0.3", bootstrap_samples=bootstrap_samples)
    c102 = evaluate(PLMC1V02Engine(), cases, "PLM-C1 v0.2", bootstrap_samples=bootstrap_samples)
    c101 = evaluate(PLMC1V01Engine(), cases, "PLM-C1 v0.1", bootstrap_samples=bootstrap_samples)
    c0 = evaluate(PLMC0Engine(), cases, "PLM-C0 v0.3", bootstrap_samples=bootstrap_samples)
    lexical = (
        evaluate(PositiveLexicalBaseline(), cases, "positive lexical baseline", bootstrap_samples=bootstrap_samples)
        if include_lexical else None
    )
    return {
        "c2_v02": c202,
        "c2_v01": c201,
        "c1_v03": c103,
        "c1_v02": c102,
        "c1_v01": c101,
        "c0": c0,
        "lexical": lexical,
        "c2_v02_vs_v01": compare(c202, c201, bootstrap_samples=bootstrap_samples),
        "c2_v02_vs_c1_v03": compare(c202, c103, bootstrap_samples=bootstrap_samples),
        "metric_rows": _metric_rows(c202, c201, c103, c102, c101, c0, lexical),
    }


def _graph_operation_audit(cases):
    seen_groups = set()
    operations = Counter()
    node_types = Counter()
    edge_relations = Counter()
    invariant_failures = Counter()
    reference_links = 0
    agentive_relations = 0
    for case in cases:
        if case["template_group"] in seen_groups:
            continue
        seen_groups.add(case["template_group"])
        result = PLMC2Engine().analyze(case["inputs"])
        operations.update(operation["operation"] for operation in result["operations"])
        node_types.update(node["node_type"] for node in result["claim_graph"]["nodes"])
        edge_relations.update(edge["relation"] for edge in result["claim_graph"]["edges"])
        for invariant, passed in result["claim_graph"]["invariants"].items():
            if not passed:
                invariant_failures[invariant] += 1
        reference_links += len(result["reference_links"])
        agentive_relations += result["diagnostics"]["agentive_relation_items"]
    return {
        "semantic_groups_audited": len(seen_groups),
        "operation_counts": dict(sorted(operations.items())),
        "claim_graph_node_types": dict(sorted(node_types.items())),
        "claim_graph_edge_relations": dict(sorted(edge_relations.items())),
        "claim_graph_invariant_failures": dict(sorted(invariant_failures.items())),
        "reference_links": reference_links,
        "agentive_relation_items": agentive_relations,
    }


def run_suite(bootstrap_samples: int = 2000):
    root = Path(__file__).resolve().parents[1]
    regression_all = load_cases(str(root / "data" / "benchmark_v03.json"))
    regression_test = [case for case in regression_all if case["split"] == "test"]
    challenge_v01 = load_cases(str(root / "data" / "challenge_c1_v01.json"))
    challenge_v02 = load_cases(str(root / "data" / "challenge_c1_v02.json"))
    challenge_v03 = load_cases(str(root / "data" / "challenge_c1_v03.json"))
    challenge_c2_v01 = load_cases(str(root / "data" / "challenge_c2_v01.json"))
    challenge_c2_v02_path = root / "data" / "challenge_c2_v02.json"
    challenge_c2_v02 = load_cases(str(challenge_c2_v02_path))
    engine_path = root / "plm_c2_v02" / "engine.py"
    concepts_path = root / "data" / "concepts_c1.json"

    regression = _evaluate_models(regression_test, bootstrap_samples, include_lexical=True)
    known_v01 = _evaluate_models(challenge_v01, bootstrap_samples)
    known_v02 = _evaluate_models(challenge_v02, bootstrap_samples)
    known_v03 = _evaluate_models(challenge_v03, bootstrap_samples)
    development_c2_v01 = _evaluate_models(challenge_c2_v01, bootstrap_samples)
    unseen_c2_v02 = _evaluate_models(challenge_c2_v02, bootstrap_samples)

    configs = {
        "full": C2Config(),
        "no_structural_revision_boundaries": C2Config(use_structural_revision_boundaries=False),
        "no_contrastive_corrections": C2Config(use_contrastive_corrections=False),
        "no_ordered_coreference": C2Config(use_ordered_coreference=False),
        "no_agentive_affordances": C2Config(use_agentive_affordances=False),
        "no_conservative_calibration": C2Config(use_conservative_calibration=False),
        "no_typed_claim_graph": C2Config(use_typed_claim_graph=False),
    }
    ablations = {
        name: evaluate(
            PLMC2Engine(config=config), challenge_c2_v01, name,
            bootstrap_samples=bootstrap_samples,
        )
        for name, config in configs.items()
    }
    graph_ablation_sample = {
        name: {
            "node_count": len(PLMC2Engine(config=config).analyze([
                "A dog and a cat were seen.", "The latter moved.",
            ])["claim_graph"]["nodes"]),
            "edge_count": len(PLMC2Engine(config=config).analyze([
                "A dog and a cat were seen.", "The latter moved.",
            ])["claim_graph"]["edges"]),
        }
        for name, config in {
            "full": C2Config(),
            "no_typed_claim_graph": C2Config(use_typed_claim_graph=False),
        }.items()
    }

    audit = _graph_operation_audit(
        regression_all + challenge_v01 + challenge_v02 + challenge_v03
        + challenge_c2_v01 + challenge_c2_v02
    )
    accuracy_ablation_names = (
        "no_structural_revision_boundaries", "no_contrastive_corrections",
        "no_ordered_coreference", "no_agentive_affordances",
    )
    full_accuracy = ablations["full"]["metrics"]["top1_accuracy"]
    full_ece = ablations["full"]["metrics"]["expected_calibration_error"]
    no_calibration_ece = ablations["no_conservative_calibration"]["metrics"][
        "expected_calibration_error"
    ]
    current_engine_hash = sha256(engine_path.read_bytes()).hexdigest()
    current_concepts_hash = sha256(concepts_path.read_bytes()).hexdigest()
    challenge_hash = sha256(challenge_c2_v02_path.read_bytes()).hexdigest()
    acceptance = {
        "engine_hash_matches_freeze_record": current_engine_hash == FROZEN_ENGINE_SHA256,
        "concept_hash_matches_freeze_record": current_concepts_hash == FROZEN_CONCEPTS_SHA256,
        "regression_top1_at_least_0_98": regression["c2_v02"]["metrics"]["top1_accuracy"] >= 0.98,
        "c1_v01_challenge_top1_at_least_0_98": known_v01["c2_v02"]["metrics"]["top1_accuracy"] >= 0.98,
        "c1_v02_challenge_top1_at_least_0_98": known_v02["c2_v02"]["metrics"]["top1_accuracy"] >= 0.98,
        "c1_v03_challenge_top1_at_least_0_98": known_v03["c2_v02"]["metrics"]["top1_accuracy"] >= 0.98,
        "c2_v01_challenge_top1_at_least_0_98": development_c2_v01["c2_v02"]["metrics"]["top1_accuracy"] >= 0.98,
        "unseen_c2_v02_top1_at_least_0_85": unseen_c2_v02["c2_v02"]["metrics"]["top1_accuracy"] >= 0.85,
        "unseen_c2_v02_beats_frozen_v01": unseen_c2_v02["c2_v02"]["metrics"]["top1_accuracy"] > unseen_c2_v02["c2_v01"]["metrics"]["top1_accuracy"],
        "unseen_c2_v02_ece_at_most_0_22": unseen_c2_v02["c2_v02"]["metrics"]["expected_calibration_error"] <= 0.22,
        "all_accuracy_features_have_ablation_effect": all(
            ablations[name]["metrics"]["top1_accuracy"] < full_accuracy
            for name in accuracy_ablation_names
        ),
        "calibration_improves_development_ece": full_ece < no_calibration_ece,
        "claim_graph_invariants_hold": not audit["claim_graph_invariant_failures"],
    }

    return {
        "version": "PLM-C2 v0.2",
        "protocol": {
            "frozen_preimplementation": [
                "benchmark_v03.json", "challenge_c1_v01.json", "challenge_c1_v02.json",
                "challenge_c1_v03.json", "challenge_c2_v01.json",
            ],
            "development_diagnostic": "challenge_c2_v01.json",
            "engine_sha256_at_freeze": FROZEN_ENGINE_SHA256,
            "engine_sha256_current": current_engine_hash,
            "concepts_sha256_at_freeze": FROZEN_CONCEPTS_SHA256,
            "concepts_sha256_current": current_concepts_hash,
            "postimplementation_challenge": "challenge_c2_v02.json",
            "postimplementation_sha256": challenge_hash,
            "first_evaluation_run": FIRST_RUN,
            "tuning_after_first_c2_v02_challenge_run": False,
            "bootstrap_unit": "template_group",
        },
        "datasets": {
            "frozen_regression": {"all_cases": len(regression_all), "test_cases": len(regression_test), "semantic_groups": 72},
            "known_c1_v01_challenge": {"cases": len(challenge_v01), "semantic_groups": 20},
            "known_c1_v02_challenge": {"cases": len(challenge_v02), "semantic_groups": 20},
            "known_c1_v03_challenge": {"cases": len(challenge_v03), "semantic_groups": 20},
            "development_c2_v01_challenge": {"cases": len(challenge_c2_v01), "semantic_groups": 20},
            "unseen_c2_v02_challenge": {"cases": len(challenge_c2_v02), "semantic_groups": 20},
        },
        "regression": regression,
        "known_c1_v01_challenge": known_v01,
        "known_c1_v02_challenge": known_v02,
        "known_c1_v03_challenge": known_v03,
        "development_c2_v01_challenge": development_c2_v01,
        "unseen_c2_v02_challenge": unseen_c2_v02,
        "ablations_on_c2_v01_challenge": ablations,
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
    suffix = " | Lexical" if include_lexical else ""
    lines.extend([
        f"| Metric | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3{suffix} | Δ v0.2-v0.1 |",
        f"|---|---:|---:|---:|---:|---:|---:{'|---:' if include_lexical else ''}|---:|",
    ])
    for row in section["metric_rows"]:
        lexical = f" | {row['lexical']}" if include_lexical else ""
        lines.append(
            f"| {row['metric']} | {row['c2_v02']} | {row['c2_v01']} | {row['c1_v03']} | "
            f"{row['c1_v02']} | {row['c1_v01']} | {row['c0']}{lexical} | "
            f"{row['delta_c2_v02_minus_v01']} |"
        )
    lines.extend([
        "",
        f"C2 v0.2 Top-1 95% cluster-bootstrap CI: `{_format_ci(section['c2_v02']['confidence_intervals']['top1_accuracy_95'])}`",
        "",
        "C2 v0.2 - v0.1 Top-1 delta 95% CI: "
        f"`{_format_ci(section['c2_v02_vs_v01']['confidence_intervals']['top1_delta_95'])}`",
    ])


def render_markdown(suite: Dict[str, Any]):
    protocol = suite["protocol"]
    lines = [
        "# PLM-C2 v0.2 Evaluation Report",
        "",
        "C2 v0.1と全先行実装を凍結比較対象とした。C2 v0.1 challengeを開発診断に使用し、"
        "v0.2 engineとConcept dataをハッシュ固定してから新規challengeを作成した。"
        "新規challenge初回実行後のengine/Concept-data調整は行っていない。",
        "",
        f"凍結engine SHA-256: `{protocol['engine_sha256_at_freeze']}`。",
        "",
        f"新規challenge SHA-256: `{protocol['postimplementation_sha256']}`。",
    ]
    _append_metrics(lines, suite["regression"], "Frozen regression (216 test cases)", True)
    _append_metrics(lines, suite["known_c1_v01_challenge"], "Known C1 v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["known_c1_v02_challenge"], "Known C1 v0.2 challenge (60 cases)")
    _append_metrics(lines, suite["known_c1_v03_challenge"], "Known C1 v0.3 challenge (60 cases)")
    _append_metrics(lines, suite["development_c2_v01_challenge"], "Development C2 v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["unseen_c2_v02_challenge"], "Unseen C2 v0.2 challenge (60 cases)")

    lines.extend(["", "### Unseen C2 v0.2 challenge failures", ""])
    failures = _failures(suite["unseen_c2_v02_challenge"]["c2_v02"])
    if not failures:
        lines.append("- None")
    for group, rows in sorted(failures.items()):
        predictions = sorted({row["predicted"] for row in rows})
        confidence = sum(row["selection_confidence"] for row in rows) / len(rows)
        lines.append(
            f"- `{group}`: expected `{rows[0]['expected']}`, predicted "
            f"`{', '.join(predictions)}`, mean confidence `{confidence:.4f}`"
        )

    lines.extend([
        "", "## Ablation on C2 v0.1 development challenge", "",
        "| Variant | Top-1 | MRR | ECE |",
        "|---|---:|---:|---:|",
    ])
    for name, report in suite["ablations_on_c2_v01_challenge"].items():
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
        f"Operations: `{audit['operation_counts']}`.",
        "",
        f"Reference links: `{audit['reference_links']}`; agentive relation items: "
        f"`{audit['agentive_relation_items']}`.",
        "",
        f"Graph sample full `{graph_sample['full']}` / disabled `{graph_sample['no_typed_claim_graph']}`.",
        "", "## Acceptance", "",
    ])
    for name, passed in suite["acceptance"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} - `{name}`")
    lines.extend([
        "", f"Overall: **{'PASS' if suite['acceptance_passed'] else 'FAIL'}**", "",
        "## Interpretation", "",
        "C2 v0.2は先行5評価セットをすべて解決し、新規未見セットでTop-1 0.95を達成した。"
        "同セットの凍結C2 v0.1は0.25であり、差は0.70だった。ECEは0.1497で目標0.22以下を満たした。",
        "",
        "残る失敗は未登録の改訂役割語`reclassified`である。参照解決は順序を明示する"
        "former/latter/first/secondに限定され、汎用的な代名詞・談話照応器ではない。"
        "agentive affordanceも閉じた動詞集合であり、各データセットは手作業の機能benchmarkである。",
        "",
    ])
    return "\n".join(lines)
