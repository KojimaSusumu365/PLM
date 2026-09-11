from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json
import random


UNRESOLVED = "UNRESOLVED"


def validate_cases(cases: List[Dict[str, Any]], concept_domains: Optional[Dict[str, str]] = None):
    required = {"id", "inputs", "domain", "expected", "tags", "split", "template_group"}
    seen = set()
    for index, case in enumerate(cases):
        missing = required - set(case)
        if missing:
            raise ValueError(f"Case {index} is missing fields: {sorted(missing)}")
        if case["id"] in seen:
            raise ValueError(f"Duplicate case id: {case['id']}")
        seen.add(case["id"])
        inputs = case["inputs"]
        if not isinstance(inputs, str) and not (
            isinstance(inputs, list) and inputs and all(isinstance(item, str) for item in inputs)
        ):
            raise ValueError(f"Case {case['id']} has invalid inputs")
        if case["split"] not in {"dev", "test"}:
            raise ValueError(f"Case {case['id']} has invalid split: {case['split']}")
        if not isinstance(case["tags"], list):
            raise ValueError(f"Case {case['id']} tags must be a list")
        if concept_domains and case["expected"] != UNRESOLVED:
            if case["expected"] not in concept_domains:
                raise ValueError(f"Case {case['id']} has unknown expected Concept")
            if concept_domains[case["expected"]] != case["domain"]:
                raise ValueError(f"Case {case['id']} expected Concept is in the wrong domain")
    return {
        "case_count": len(cases),
        "template_groups": len({case["template_group"] for case in cases}),
        "splits": {
            split: sum(case["split"] == split for case in cases)
            for split in ("dev", "test")
        },
    }


def load_cases(path: Optional[str] = None, split: Optional[str] = None) -> List[Dict[str, Any]]:
    path = path or (Path(__file__).resolve().parents[1] / "data" / "benchmark_v03.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    cases = payload["cases"]
    validate_cases(cases)
    if split and split != "all":
        if split not in {"dev", "test"}:
            raise ValueError(f"Unknown split: {split}")
        cases = [case for case in cases if case["split"] == split]
    return cases


def _rank_of(expected: str, result: Dict[str, Any], domain: str) -> Optional[int]:
    if expected == UNRESOLVED:
        return 1 if result["selections"][domain]["selected"] == UNRESOLVED else None
    for index, row in enumerate(result["ranking"][domain], start=1):
        has_signal = row.get("score", 0.0) > 0 or any(
            row.get(field, 0.0) > 0
            for field in ("direct_support", "propagated_support", "context_boost")
        )
        if row["concept"] == expected:
            return index if has_signal else None
    return None


def _percentile(values: List[float], probability: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _cluster_bootstrap_accuracy(rows, samples: int, seed: int):
    groups = defaultdict(list)
    for row in rows:
        groups[row["template_group"]].append(row)
    keys = sorted(groups)
    if not keys or samples <= 0:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        selected = [rng.choice(keys) for _ in keys]
        sample_rows = [row for key in selected for row in groups[key]]
        values.append(sum(row["top1_correct"] for row in sample_rows) / len(sample_rows))
    return {
        "lower": round(_percentile(values, 0.025), 4),
        "upper": round(_percentile(values, 0.975), 4),
        "method": "template-group cluster percentile bootstrap",
        "samples": samples,
        "clusters": len(keys),
        "seed": seed,
    }


def _paired_cluster_bootstrap_delta(primary_rows, baseline_rows, samples: int, seed: int):
    baseline_by_id = {row["id"]: row for row in baseline_rows}
    groups = defaultdict(list)
    for row in primary_rows:
        other = baseline_by_id[row["id"]]
        groups[row["template_group"]].append(
            int(row["top1_correct"]) - int(other["top1_correct"])
        )
    keys = sorted(groups)
    rng = random.Random(seed)
    values = []
    for _ in range(samples):
        selected = [rng.choice(keys) for _ in keys]
        differences = [value for key in selected for value in groups[key]]
        values.append(sum(differences) / len(differences))
    return {
        "lower": round(_percentile(values, 0.025), 4),
        "upper": round(_percentile(values, 0.975), 4),
        "method": "paired template-group cluster percentile bootstrap",
        "samples": samples,
        "clusters": len(keys),
        "seed": seed,
    }


def _macro_scores(rows):
    labels = sorted({row["expected"] for row in rows} | {row["predicted"] for row in rows})
    per_label = {}
    for label in labels:
        true_positive = sum(row["expected"] == label and row["predicted"] == label for row in rows)
        false_positive = sum(row["expected"] != label and row["predicted"] == label for row in rows)
        false_negative = sum(row["expected"] == label and row["predicted"] != label for row in rows)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {
            "support": sum(row["expected"] == label for row in rows),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    return {
        "macro_precision": round(sum(row["precision"] for row in per_label.values()) / len(labels), 4),
        "macro_recall": round(sum(row["recall"] for row in per_label.values()) / len(labels), 4),
        "macro_f1": round(sum(row["f1"] for row in per_label.values()) / len(labels), 4),
        "per_label": per_label,
    }


def _calibration(rows, bin_count: int = 10):
    bins = []
    calibration_error = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [
            row for row in rows
            if lower <= row["selection_confidence"] < upper
            or (index == bin_count - 1 and row["selection_confidence"] == 1.0)
        ]
        if not members:
            continue
        confidence = sum(row["selection_confidence"] for row in members) / len(members)
        accuracy = sum(row["top1_correct"] for row in members) / len(members)
        calibration_error += len(members) / len(rows) * abs(accuracy - confidence)
        bins.append({
            "lower": lower,
            "upper": upper,
            "count": len(members),
            "mean_confidence": round(confidence, 4),
            "accuracy": round(accuracy, 4),
        })
    brier = sum(
        (row["selection_confidence"] - float(row["top1_correct"])) ** 2
        for row in rows
    ) / len(rows)
    return {
        "expected_calibration_error": round(calibration_error, 4),
        "brier_score": round(brier, 4),
        "bins": bins,
    }


def _coverage_accuracy(rows):
    curve = []
    for threshold in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
        accepted = [
            row for row in rows
            if row["predicted"] != UNRESOLVED and row["selection_confidence"] >= threshold
        ]
        curve.append({
            "threshold": threshold,
            "coverage": round(len(accepted) / len(rows), 4),
            "accuracy": round(sum(row["top1_correct"] for row in accepted) / len(accepted), 4)
            if accepted else None,
            "accepted": len(accepted),
        })
    return curve


def evaluate(
    engine,
    cases: Iterable[Dict[str, Any]],
    name: str,
    top_k: int = 5,
    bootstrap_samples: int = 2000,
    seed: int = 1701,
) -> Dict[str, Any]:
    cases = list(cases)
    case_rows = []
    tag_stats = defaultdict(lambda: {"count": 0, "top1": 0, "topk": 0, "rr": 0.0})
    expected_unresolved = predicted_unresolved = correct_unresolved = 0
    contradiction_total = contradiction_pass = 0
    minority_total = minority_retained = 0
    candidates_evaluated = patterns_checked = overlap_suppressed = 0

    for case in cases:
        result = engine.analyze(case["inputs"])
        domain = case["domain"]
        expected = case["expected"]
        selection = result["selections"][domain]
        predicted = selection["selected"]
        rank = _rank_of(expected, result, domain)
        top1 = predicted == expected
        topk = rank is not None and rank <= top_k
        reciprocal_rank = 0.0 if rank is None else 1.0 / rank
        forbidden = case.get("forbidden", [])
        contradiction_ok = predicted not in forbidden if forbidden else None
        confidence = max(0.0, min(1.0, float(selection.get("selection_confidence", 0.0))))

        if expected == UNRESOLVED:
            expected_unresolved += 1
        if predicted == UNRESOLVED:
            predicted_unresolved += 1
            if expected == UNRESOLVED:
                correct_unresolved += 1
        if forbidden:
            contradiction_total += 1
            contradiction_pass += int(bool(contradiction_ok))
        if "minority_evidence" in case.get("tags", []):
            minority_total += 1
            minority_retained += int(topk)

        for tag in case.get("tags", []):
            tag_stats[tag]["count"] += 1
            tag_stats[tag]["top1"] += int(top1)
            tag_stats[tag]["topk"] += int(topk)
            tag_stats[tag]["rr"] += reciprocal_rank

        diagnostics = result.get("diagnostics", {})
        candidates_evaluated += diagnostics.get(
            "candidates_by_domain", {}
        ).get(domain, len(result["ranking"][domain]))
        patterns_checked += diagnostics.get("patterns_checked", 0)
        overlap_suppressed += diagnostics.get("overlap_matches_suppressed", 0)
        case_rows.append({
            "id": case["id"],
            "template_group": case["template_group"],
            "split": case["split"],
            "domain": domain,
            "expected": expected,
            "predicted": predicted,
            "selection_confidence": round(confidence, 4),
            "rank": rank,
            "top1_correct": top1,
            f"top{top_k}_hit": topk,
            "reciprocal_rank": round(reciprocal_rank, 4),
            "contradiction_rejected": contradiction_ok,
            "tags": case.get("tags", []),
        })

    count = len(case_rows)
    if not count:
        raise ValueError("Cannot evaluate an empty case set")
    top1_correct = sum(row["top1_correct"] for row in case_rows)
    topk_hits = sum(row[f"top{top_k}_hit"] for row in case_rows)
    macro = _macro_scores(case_rows)
    calibration = _calibration(case_rows)
    per_tag = {
        tag: {
            "count": values["count"],
            "top1_accuracy": round(values["top1"] / values["count"], 4),
            f"top{top_k}_recall": round(values["topk"] / values["count"], 4),
            "mrr": round(values["rr"] / values["count"], 4),
        }
        for tag, values in sorted(tag_stats.items())
    }
    return {
        "model": name,
        "case_count": count,
        "template_groups": len({row["template_group"] for row in case_rows}),
        "metrics": {
            "top1_accuracy": round(top1_correct / count, 4),
            f"top{top_k}_recall": round(topk_hits / count, 4),
            "mrr": round(sum(row["reciprocal_rank"] for row in case_rows) / count, 4),
            "macro_precision": macro["macro_precision"],
            "macro_recall": macro["macro_recall"],
            "macro_f1": macro["macro_f1"],
            "unresolved_precision": round(correct_unresolved / predicted_unresolved, 4)
            if predicted_unresolved else None,
            "unresolved_recall": round(correct_unresolved / expected_unresolved, 4)
            if expected_unresolved else None,
            "minority_evidence_retention": round(minority_retained / minority_total, 4)
            if minority_total else None,
            "contradiction_rejection": round(contradiction_pass / contradiction_total, 4)
            if contradiction_total else None,
            "coverage": round(sum(row["predicted"] != UNRESOLVED for row in case_rows) / count, 4),
            "selective_accuracy": round(
                sum(row["top1_correct"] and row["predicted"] != UNRESOLVED for row in case_rows)
                / sum(row["predicted"] != UNRESOLVED for row in case_rows),
                4,
            ) if any(row["predicted"] != UNRESOLVED for row in case_rows) else None,
            "expected_calibration_error": calibration["expected_calibration_error"],
            "brier_score": calibration["brier_score"],
            "average_candidates_evaluated": round(candidates_evaluated / count, 2),
            "average_patterns_checked": round(patterns_checked / count, 2),
            "average_overlap_matches_suppressed": round(overlap_suppressed / count, 2),
        },
        "confidence_intervals": {
            "top1_accuracy_95": _cluster_bootstrap_accuracy(case_rows, bootstrap_samples, seed),
        },
        "coverage_accuracy_curve": _coverage_accuracy(case_rows),
        "calibration_bins": calibration["bins"],
        "per_label": macro["per_label"],
        "per_tag": per_tag,
        "counts": {
            "top1_correct": top1_correct,
            f"top{top_k}_hits": topk_hits,
            "expected_unresolved": expected_unresolved,
            "predicted_unresolved": predicted_unresolved,
            "correct_unresolved": correct_unresolved,
            "minority_cases": minority_total,
            "minority_retained": minority_retained,
            "contradiction_cases": contradiction_total,
            "contradiction_rejected": contradiction_pass,
            "total_candidates_evaluated": candidates_evaluated,
            "total_patterns_checked": patterns_checked,
            "total_overlap_matches_suppressed": overlap_suppressed,
        },
        "cases": case_rows,
    }


def compare(primary: Dict[str, Any], baseline: Dict[str, Any], bootstrap_samples: int = 2000, seed: int = 1701):
    deltas = {}
    for metric, value in primary["metrics"].items():
        baseline_value = baseline["metrics"].get(metric)
        if isinstance(value, (int, float)) and isinstance(baseline_value, (int, float)):
            deltas[metric] = round(value - baseline_value, 4)
    return {
        "primary": primary,
        "baseline": baseline,
        "delta_primary_minus_baseline": deltas,
        "confidence_intervals": {
            "top1_delta_95": _paired_cluster_bootstrap_delta(
                primary["cases"], baseline["cases"], bootstrap_samples, seed
            ),
        },
    }


def _format_ci(interval):
    if not interval:
        return "n/a"
    return f"[{interval['lower']:.4f}, {interval['upper']:.4f}]"


def render_markdown(suite: Dict[str, Any]) -> str:
    test = suite["splits"]["test"]
    primary = test["primary"]
    baseline = test["baseline"]
    delta = test["delta_primary_minus_baseline"]
    keys = [
        "top1_accuracy", "top5_recall", "mrr", "macro_f1",
        "unresolved_precision", "unresolved_recall", "minority_evidence_retention",
        "contradiction_rejection", "coverage", "selective_accuracy",
        "expected_calibration_error", "brier_score",
        "average_candidates_evaluated", "average_patterns_checked",
    ]
    lines = [
        "# PLM-C0 v0.3 Evaluation Report",
        "",
        f"Benchmark: **{suite['dataset']['case_count']} cases** "
        f"({suite['dataset']['dev_cases']} dev / {suite['dataset']['test_cases']} test), "
        f"{suite['dataset']['template_groups']} semantic template groups.",
        "",
        "## Held-out wrapper test split",
        "",
        "| Metric | PLM-C0 v0.3 | Positive lexical baseline | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in keys:
        lines.append(
            f"| {key} | {primary['metrics'].get(key)} | "
            f"{baseline['metrics'].get(key)} | {delta.get(key)} |"
        )
    lines.extend([
        "",
        f"PLM Top-1 95% CI: {_format_ci(primary['confidence_intervals']['top1_accuracy_95'])}",
        "",
        f"Paired Top-1 delta 95% CI: {_format_ci(test['confidence_intervals']['top1_delta_95'])}",
        "",
        "## Ablation study (test split)",
        "",
        "| Variant | Top-1 | Macro-F1 | UNRESOLVED F1 | Contradiction rejection | ECE |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for name, report in suite["ablations"].items():
        unresolved_f1 = report["per_label"].get(UNRESOLVED, {}).get("f1")
        lines.append(
            f"| {name} | {report['metrics']['top1_accuracy']} | {report['metrics']['macro_f1']} | "
            f"{unresolved_f1} | {report['metrics']['contradiction_rejection']} | "
            f"{report['metrics']['expected_calibration_error']} |"
        )
    lines.extend([
        "",
        "## Selected tag breakdown (test split)",
        "",
        "| Tag | Cases | PLM Top-1 | Baseline Top-1 | PLM Top-5 |",
        "|---|---:|---:|---:|---:|",
    ])
    for tag in (
        "stress", "negation", "context_scope", "correction", "boundary",
        "hierarchy", "minority_evidence",
    ):
        primary_tag = primary["per_tag"].get(tag)
        baseline_tag = baseline["per_tag"].get(tag)
        if primary_tag and baseline_tag:
            lines.append(
                f"| {tag} | {primary_tag['count']} | {primary_tag['top1_accuracy']} | "
                f"{baseline_tag['top1_accuracy']} | {primary_tag['top5_recall']} |"
            )
    lines.extend([
        "",
        "## Coverage-accuracy (PLM test split)",
        "",
        "| Confidence threshold | Coverage | Accuracy among accepted | Accepted |",
        "|---:|---:|---:|---:|",
    ])
    for row in primary["coverage_accuracy_curve"]:
        lines.append(
            f"| {row['threshold']} | {row['coverage']} | {row['accuracy']} | {row['accepted']} |"
        )
    lines.extend([
        "",
        "## PLM errors on test split",
        "",
    ])
    errors = [row for row in primary["cases"] if not row["top1_correct"]]
    if errors:
        error_groups = defaultdict(list)
        for row in errors:
            error_groups[row["template_group"]].append(row)
        for group, rows in sorted(error_groups.items()):
            predictions = sorted({row["predicted"] for row in rows})
            mean_confidence = sum(row["selection_confidence"] for row in rows) / len(rows)
            lines.append(
                f"- `{group}` ({len(rows)} wrapper variants): expected `{rows[0]['expected']}`, "
                f"predicted `{', '.join(predictions)}`, mean confidence `{mean_confidence:.4f}`"
            )
    else:
        lines.append("- None")
    lines.extend([
        "",
        "## Interpretation limits",
        "",
        "- This is a deterministic, closed-vocabulary functional benchmark, not an external corpus.",
        "- Dev and test use different wrappers but share 72 semantic seeds; this is not a fully independent blind test.",
        "- Confidence intervals cluster by semantic template group to avoid treating wrapper variants as independent examples.",
        "- Calibration metrics assess the current heuristic confidence, not a trained probability model.",
        "",
    ])
    return "\n".join(lines)
