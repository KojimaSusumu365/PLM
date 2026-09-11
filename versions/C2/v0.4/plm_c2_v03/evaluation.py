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
from plm_c2_v02 import PLMC2Engine as PLMC2V02Engine

from .engine import C2Config, PLMC2Engine


FROZEN_ENGINE_SHA256 = "95dc8f75e9a5e727d674251056a92850c954995d04bb24d1d89d087fb542cb51"
FROZEN_CONCEPTS_SHA256 = "740b467d5c1e4d1834c7663c8c1d47e147fa6e6cbf26059171e1a950e550575d"
FROZEN_DEVELOPMENT_SHA256 = "2e0821e504f03242424ca91cfe94b5b4ba9ac42129854a71137deafdbf546e5c"
FIRST_RUN = {
    "top1_accuracy": 0.9583,
    "mrr": 0.9688,
    "expected_calibration_error": 0.0998,
    "failure_groups": ["revision_reidentified"],
}
METRIC_KEYS = (
    "top1_accuracy", "top5_recall", "mrr", "macro_f1",
    "unresolved_precision", "unresolved_recall", "contradiction_rejection",
    "coverage", "selective_accuracy", "expected_calibration_error", "brier_score",
)


def _metric_rows(c203, c202, c201, c103, c102, c101, c0, lexical=None):
    rows = []
    for key in METRIC_KEYS:
        value = c203["metrics"].get(key)
        old_value = c202["metrics"].get(key)
        rows.append({
            "metric": key,
            "c2_v03": value,
            "c2_v02": old_value,
            "c2_v01": c201["metrics"].get(key),
            "c1_v03": c103["metrics"].get(key),
            "c1_v02": c102["metrics"].get(key),
            "c1_v01": c101["metrics"].get(key),
            "c0": c0["metrics"].get(key),
            "lexical": lexical["metrics"].get(key) if lexical else None,
            "delta_c2_v03_minus_v02": round(value - old_value, 4)
            if isinstance(value, (int, float)) and isinstance(old_value, (int, float)) else None,
        })
    return rows


def _evaluate_models(cases, bootstrap_samples, include_lexical=False):
    c203 = evaluate(PLMC2Engine(), cases, "PLM-C2 v0.3", bootstrap_samples=bootstrap_samples)
    c202 = evaluate(PLMC2V02Engine(), cases, "PLM-C2 v0.2", bootstrap_samples=bootstrap_samples)
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
        "c2_v03": c203,
        "c2_v02": c202,
        "c2_v01": c201,
        "c1_v03": c103,
        "c1_v02": c102,
        "c1_v01": c101,
        "c0": c0,
        "lexical": lexical,
        "c2_v03_vs_v02": compare(c203, c202, bootstrap_samples=bootstrap_samples),
        "c2_v03_vs_c1_v03": compare(c203, c103, bootstrap_samples=bootstrap_samples),
        "metric_rows": _metric_rows(c203, c202, c201, c103, c102, c101, c0, lexical),
    }


def _graph_relation_audit(cases):
    seen_groups = set()
    operations = Counter()
    node_types = Counter()
    edge_relations = Counter()
    frame_types = Counter()
    frame_voices = Counter()
    invariant_failures = Counter()
    contract_failures = 0
    relation_frames = 0
    for case in cases:
        group_key = (case["template_group"], tuple(case.get("tags", [])))
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        result = PLMC2Engine().analyze(case["inputs"])
        operations.update(operation["operation"] for operation in result["operations"])
        node_types.update(node["node_type"] for node in result["claim_graph"]["nodes"])
        edge_relations.update(edge["relation"] for edge in result["claim_graph"]["edges"])
        frame_types.update(frame["relation_type"] for frame in result["relation_frames"])
        frame_voices.update(frame["voice"] for frame in result["relation_frames"])
        relation_frames += len(result["relation_frames"])
        for invariant, passed in result["claim_graph"]["invariants"].items():
            if not passed:
                invariant_failures[invariant] += 1
        contract_failures += int(not result["relation_contract"]["ready_for_r1_experiment"])
    return {
        "semantic_groups_audited": len(seen_groups),
        "operation_counts": dict(sorted(operations.items())),
        "claim_graph_node_types": dict(sorted(node_types.items())),
        "claim_graph_edge_relations": dict(sorted(edge_relations.items())),
        "relation_frame_types": dict(sorted(frame_types.items())),
        "relation_frame_voices": dict(sorted(frame_voices.items())),
        "relation_frames": relation_frames,
        "claim_graph_invariant_failures": dict(sorted(invariant_failures.items())),
        "relation_contract_failures": contract_failures,
    }


def _failure_groups(report):
    return sorted({row["template_group"] for row in report["cases"] if not row["top1_correct"]})


def run_suite(bootstrap_samples: int = 2000):
    root = Path(__file__).resolve().parents[1]
    regression_all = load_cases(str(root / "data" / "benchmark_v03.json"))
    regression_test = [case for case in regression_all if case["split"] == "test"]
    paths = {
        "c1_v01": root / "data" / "challenge_c1_v01.json",
        "c1_v02": root / "data" / "challenge_c1_v02.json",
        "c1_v03": root / "data" / "challenge_c1_v03.json",
        "c2_v01": root / "data" / "challenge_c2_v01.json",
        "c2_v02": root / "data" / "challenge_c2_v02.json",
        "development_v03": root / "data" / "development_c2_v03.json",
        "c2_v03": root / "data" / "challenge_c2_v03.json",
    }
    datasets = {name: load_cases(str(path)) for name, path in paths.items()}

    regression = _evaluate_models(regression_test, bootstrap_samples, include_lexical=True)
    evaluated = {
        name: _evaluate_models(cases, bootstrap_samples)
        for name, cases in datasets.items()
    }

    configs = {
        "full": C2Config(),
        "no_generalized_revision_roles": C2Config(use_generalized_revision_roles=False),
        "no_extended_coreference": C2Config(use_extended_coreference=False),
        "no_role_affordances": C2Config(use_role_affordances=False),
        "no_japanese_correction_scope": C2Config(use_japanese_correction_scope=False),
        "no_relation_frames": C2Config(use_relation_frames=False),
        "no_relation_aware_calibration": C2Config(use_relation_aware_calibration=False),
    }
    development_cases = datasets["development_v03"]
    ablations = {
        name: evaluate(
            PLMC2Engine(config=config), development_cases, name,
            bootstrap_samples=bootstrap_samples,
        )
        for name, config in configs.items()
    }
    graph_ablation_sample = {
        name: {
            "node_count": len(result["claim_graph"]["nodes"]),
            "edge_count": len(result["claim_graph"]["edges"]),
            "frame_count": len(result["relation_frames"]),
            "r1_ready": result["relation_contract"]["ready_for_r1_experiment"],
        }
        for name, result in (
            ("full", PLMC2Engine().analyze("The bank granted aid to a river project.")),
            (
                "no_relation_frames",
                PLMC2Engine(config=C2Config(use_relation_frames=False)).analyze(
                    "The bank granted aid to a river project."
                ),
            ),
        )
    }

    audit_cases = regression_all
    for cases in datasets.values():
        audit_cases += cases
    audit = _graph_relation_audit(audit_cases)
    full_accuracy = ablations["full"]["metrics"]["top1_accuracy"]
    full_ece = ablations["full"]["metrics"]["expected_calibration_error"]
    no_calibration_ece = ablations["no_relation_aware_calibration"]["metrics"][
        "expected_calibration_error"
    ]
    engine_hash = sha256((root / "plm_c2_v03" / "engine.py").read_bytes()).hexdigest()
    concepts_hash = sha256((root / "data" / "concepts_c1.json").read_bytes()).hexdigest()
    development_hash = sha256(paths["development_v03"].read_bytes()).hexdigest()
    challenge_hash = sha256(paths["c2_v03"].read_bytes()).hexdigest()
    unseen = evaluated["c2_v03"]
    first_run_reproduced = (
        unseen["c2_v03"]["metrics"]["top1_accuracy"] == FIRST_RUN["top1_accuracy"]
        and unseen["c2_v03"]["metrics"]["mrr"] == FIRST_RUN["mrr"]
        and unseen["c2_v03"]["metrics"]["expected_calibration_error"]
        == FIRST_RUN["expected_calibration_error"]
        and _failure_groups(unseen["c2_v03"]) == FIRST_RUN["failure_groups"]
    )
    accuracy_ablation_names = (
        "no_generalized_revision_roles", "no_extended_coreference",
        "no_role_affordances", "no_japanese_correction_scope",
    )
    prior_sections = [
        regression,
        evaluated["c1_v01"], evaluated["c1_v02"], evaluated["c1_v03"],
        evaluated["c2_v01"], evaluated["c2_v02"],
    ]
    required_frame_types = {"COREFERENCE", "REVISION", "FINANCIAL_AFFORDANCE", "SPATIAL_ASSOCIATION"}
    acceptance = {
        "engine_hash_matches_freeze_record": engine_hash == FROZEN_ENGINE_SHA256,
        "concept_hash_matches_freeze_record": concepts_hash == FROZEN_CONCEPTS_SHA256,
        "development_hash_matches_freeze_record": development_hash == FROZEN_DEVELOPMENT_SHA256,
        "all_prior_sets_top1_at_least_0_98": all(
            section["c2_v03"]["metrics"]["top1_accuracy"] >= 0.98
            for section in prior_sections
        ),
        "development_top1_at_least_0_98": evaluated["development_v03"]["c2_v03"]["metrics"]["top1_accuracy"] >= 0.98,
        "unseen_c2_v03_top1_at_least_0_90": unseen["c2_v03"]["metrics"]["top1_accuracy"] >= 0.90,
        "unseen_c2_v03_beats_frozen_v02": unseen["c2_v03"]["metrics"]["top1_accuracy"] > unseen["c2_v02"]["metrics"]["top1_accuracy"],
        "unseen_c2_v03_ece_at_most_0_15": unseen["c2_v03"]["metrics"]["expected_calibration_error"] <= 0.15,
        "first_unseen_run_is_reproduced": first_run_reproduced,
        "all_accuracy_features_have_ablation_effect": all(
            ablations[name]["metrics"]["top1_accuracy"] < full_accuracy
            for name in accuracy_ablation_names
        ),
        "relation_calibration_improves_development_ece": full_ece < no_calibration_ece,
        "relation_frame_ablation_removes_frames": (
            graph_ablation_sample["full"]["frame_count"] > 0
            and graph_ablation_sample["no_relation_frames"]["frame_count"] == 0
            and not graph_ablation_sample["no_relation_frames"]["r1_ready"]
        ),
        "required_relation_frame_types_observed": required_frame_types <= set(audit["relation_frame_types"]),
        "claim_graph_invariants_hold": not audit["claim_graph_invariant_failures"],
        "relation_contracts_are_r1_ready": audit["relation_contract_failures"] == 0,
    }

    return {
        "version": "PLM-C2 v0.3",
        "protocol": {
            "frozen_preimplementation": [
                "benchmark_v03.json", "challenge_c1_v01.json", "challenge_c1_v02.json",
                "challenge_c1_v03.json", "challenge_c2_v01.json", "challenge_c2_v02.json",
            ],
            "development_diagnostic": "development_c2_v03.json",
            "engine_sha256_at_freeze": FROZEN_ENGINE_SHA256,
            "engine_sha256_current": engine_hash,
            "concepts_sha256_at_freeze": FROZEN_CONCEPTS_SHA256,
            "concepts_sha256_current": concepts_hash,
            "development_sha256": development_hash,
            "postimplementation_challenge": "challenge_c2_v03.json",
            "postimplementation_sha256": challenge_hash,
            "first_evaluation_run": FIRST_RUN,
            "tuning_after_first_c2_v03_challenge_run": False,
            "external_corpus": False,
            "bootstrap_unit": "template_group",
        },
        "datasets": {
            "frozen_regression": {"test_cases": len(regression_test), "semantic_groups": 72},
            **{
                name: {"cases": len(cases), "semantic_groups": len({case["template_group"] for case in cases})}
                for name, cases in datasets.items()
            },
        },
        "regression": regression,
        "known_c1_v01_challenge": evaluated["c1_v01"],
        "known_c1_v02_challenge": evaluated["c1_v02"],
        "known_c1_v03_challenge": evaluated["c1_v03"],
        "known_c2_v01_challenge": evaluated["c2_v01"],
        "known_c2_v02_challenge": evaluated["c2_v02"],
        "development_c2_v03": evaluated["development_v03"],
        "unseen_c2_v03_challenge": unseen,
        "ablations_on_c2_v03_development": ablations,
        "graph_ablation_sample": graph_ablation_sample,
        "graph_relation_audit": audit,
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
        f"| Metric | C2 v0.3 | C2 v0.2 | C2 v0.1 | C1 v0.3 | C1 v0.2 | C1 v0.1 | C0 v0.3{suffix} | Δ v0.3-v0.2 |",
        f"|---|---:|---:|---:|---:|---:|---:|---:{'|---:' if include_lexical else ''}|---:|",
    ])
    for row in section["metric_rows"]:
        lexical = f" | {row['lexical']}" if include_lexical else ""
        lines.append(
            f"| {row['metric']} | {row['c2_v03']} | {row['c2_v02']} | {row['c2_v01']} | "
            f"{row['c1_v03']} | {row['c1_v02']} | {row['c1_v01']} | {row['c0']}"
            f"{lexical} | {row['delta_c2_v03_minus_v02']} |"
        )
    lines.extend([
        "",
        f"C2 v0.3 Top-1 95% cluster-bootstrap CI: `{_format_ci(section['c2_v03']['confidence_intervals']['top1_accuracy_95'])}`",
        "",
        "C2 v0.3 - v0.2 Top-1 delta 95% CI: "
        f"`{_format_ci(section['c2_v03_vs_v02']['confidence_intervals']['top1_delta_95'])}`",
    ])


def render_markdown(suite: Dict[str, Any]):
    protocol = suite["protocol"]
    lines = [
        "# PLM-C2 v0.3 Evaluation Report",
        "",
        "C2 v0.2と全先行実装を凍結比較対象とした。v0.3 development setで機能診断後、"
        "engineとConcept dataをハッシュ固定して新規challengeを作成した。"
        "初回challenge実行後のengine/Concept-data調整は行っていない。",
        "",
        f"凍結engine SHA-256: `{protocol['engine_sha256_at_freeze']}`。",
        "",
        f"新規challenge SHA-256: `{protocol['postimplementation_sha256']}`。",
    ]
    _append_metrics(lines, suite["regression"], "Frozen regression (216 test cases)", True)
    _append_metrics(lines, suite["known_c1_v01_challenge"], "Known C1 v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["known_c1_v02_challenge"], "Known C1 v0.2 challenge (60 cases)")
    _append_metrics(lines, suite["known_c1_v03_challenge"], "Known C1 v0.3 challenge (60 cases)")
    _append_metrics(lines, suite["known_c2_v01_challenge"], "Known C2 v0.1 challenge (60 cases)")
    _append_metrics(lines, suite["known_c2_v02_challenge"], "Known C2 v0.2 challenge (60 cases)")
    _append_metrics(lines, suite["development_c2_v03"], "C2 v0.3 development diagnostic (30 cases)")
    _append_metrics(lines, suite["unseen_c2_v03_challenge"], "Unseen C2 v0.3 challenge (72 cases)")

    lines.extend(["", "### Unseen C2 v0.3 challenge failures", ""])
    failures = _failures(suite["unseen_c2_v03_challenge"]["c2_v03"])
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
        "", "## Ablation on C2 v0.3 development diagnostic", "",
        "| Variant | Top-1 | MRR | ECE |",
        "|---|---:|---:|---:|",
    ])
    for name, report in suite["ablations_on_c2_v03_development"].items():
        metrics = report["metrics"]
        lines.append(
            f"| {name} | {metrics['top1_accuracy']} | {metrics['mrr']} | "
            f"{metrics['expected_calibration_error']} |"
        )

    audit = suite["graph_relation_audit"]
    sample = suite["graph_ablation_sample"]
    lines.extend([
        "", "## Relation contract and Claim Graph audit", "",
        f"Semantic groups audited: `{audit['semantic_groups_audited']}`; "
        f"graph invariant failures: `{audit['claim_graph_invariant_failures']}`; "
        f"contract failures: `{audit['relation_contract_failures']}`.",
        "",
        f"Relation frames: `{audit['relation_frames']}`; types: `{audit['relation_frame_types']}`; "
        f"voices: `{audit['relation_frame_voices']}`.",
        "",
        f"Node types: `{audit['claim_graph_node_types']}`.",
        "",
        f"Edge relations: `{audit['claim_graph_edge_relations']}`.",
        "",
        f"Operations: `{audit['operation_counts']}`.",
        "",
        f"Frame sample full `{sample['full']}` / disabled `{sample['no_relation_frames']}`.",
        "", "## Acceptance", "",
    ])
    for name, passed in suite["acceptance"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} - `{name}`")
    lines.extend([
        "", f"Overall: **{'PASS' if suite['acceptance_passed'] else 'FAIL'}**", "",
        "## Interpretation", "",
        "C2 v0.3は先行6評価セットと開発診断をすべて解決し、新規未見セットでTop-1 0.9583を達成した。"
        "同セットの凍結C2 v0.2は0.4167で、差は0.5416だった。ECEは0.0998で目標0.15以下を満たした。",
        "",
        "Relation Frame契約とClaim Graph schema v2は全監査ケースで整合し、R1実験開始条件を満たした。"
        "ただし、未見失敗`reidentified`が示すように改訂役割はまだ閉じた形態意味集合である。"
        "評価は同一開発セッションで作成した手作業benchmarkであり、外部コーパスではない。",
        "",
    ])
    return "\n".join(lines)
