from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json


def load_cases(path: Optional[str] = None) -> List[Dict[str, Any]]:
    path = path or (Path(__file__).resolve().parents[1] / "data" / "eval_cases.json")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload["cases"]


def _rank_of(expected: str, result: Dict[str, Any], domain: str) -> Optional[int]:
    if expected == "UNRESOLVED":
        return 1 if result["selections"][domain]["selected"] == "UNRESOLVED" else None
    for index, row in enumerate(result["ranking"][domain], start=1):
        has_signal = row.get("score", 0.0) > 0 or any(
            row.get(field, 0.0) > 0
            for field in ("direct_support", "propagated_support", "context_boost")
        )
        if row["concept"] == expected:
            return index if has_signal else None
    return None


def evaluate(engine, cases: Iterable[Dict[str, Any]], name: str, top_k: int = 5) -> Dict[str, Any]:
    case_rows = []
    tag_stats = defaultdict(lambda: {"count": 0, "top1_correct": 0})
    expected_unresolved = predicted_unresolved = correct_unresolved = 0
    contradiction_total = contradiction_pass = 0
    minority_total = minority_retained = 0
    candidates_evaluated = patterns_checked = 0

    for case in cases:
        result = engine.analyze(case["inputs"])
        domain = case["domain"]
        expected = case["expected"]
        predicted = result["selections"][domain]["selected"]
        rank = _rank_of(expected, result, domain)
        top1 = predicted == expected
        topk = rank is not None and rank <= top_k
        reciprocal_rank = 0.0 if rank is None else 1.0 / rank
        forbidden = case.get("forbidden", [])
        contradiction_ok = predicted not in forbidden if forbidden else None

        if expected == "UNRESOLVED":
            expected_unresolved += 1
        if predicted == "UNRESOLVED":
            predicted_unresolved += 1
            if expected == "UNRESOLVED":
                correct_unresolved += 1
        if forbidden:
            contradiction_total += 1
            contradiction_pass += int(bool(contradiction_ok))
        if "minority_evidence" in case.get("tags", []):
            minority_total += 1
            minority_retained += int(topk)

        for tag in case.get("tags", []):
            tag_stats[tag]["count"] += 1
            tag_stats[tag]["top1_correct"] += int(top1)

        diagnostics = result.get("diagnostics", {})
        candidates_evaluated += diagnostics.get("candidates_by_domain", {}).get(domain, len(result["ranking"][domain]))
        patterns_checked += diagnostics.get("patterns_checked", 0)
        case_rows.append({
            "id": case["id"],
            "domain": domain,
            "expected": expected,
            "predicted": predicted,
            "rank": rank,
            "top1_correct": top1,
            f"top{top_k}_hit": topk,
            "reciprocal_rank": round(reciprocal_rank, 4),
            "contradiction_rejected": contradiction_ok,
            "tags": case.get("tags", []),
        })

    n = len(case_rows)
    top1_correct = sum(row["top1_correct"] for row in case_rows)
    topk_hits = sum(row[f"top{top_k}_hit"] for row in case_rows)
    mrr = sum(row["reciprocal_rank"] for row in case_rows) / n if n else 0.0
    per_tag = {
        tag: {
            "count": values["count"],
            "top1_accuracy": round(values["top1_correct"] / values["count"], 4),
        }
        for tag, values in sorted(tag_stats.items())
    }
    return {
        "model": name,
        "case_count": n,
        "metrics": {
            "top1_accuracy": round(top1_correct / n, 4) if n else 0.0,
            f"top{top_k}_recall": round(topk_hits / n, 4) if n else 0.0,
            "mrr": round(mrr, 4),
            "unresolved_precision": round(correct_unresolved / predicted_unresolved, 4) if predicted_unresolved else None,
            "unresolved_recall": round(correct_unresolved / expected_unresolved, 4) if expected_unresolved else None,
            "minority_evidence_retention": round(minority_retained / minority_total, 4) if minority_total else None,
            "contradiction_rejection": round(contradiction_pass / contradiction_total, 4) if contradiction_total else None,
            "average_candidates_evaluated": round(candidates_evaluated / n, 2) if n else 0.0,
            "average_patterns_checked": round(patterns_checked / n, 2) if n else 0.0,
        },
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
        },
        "per_tag": per_tag,
        "cases": case_rows,
    }


def compare(primary: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    deltas = {}
    for metric, value in primary["metrics"].items():
        base_value = baseline["metrics"].get(metric)
        if isinstance(value, (int, float)) and isinstance(base_value, (int, float)):
            deltas[metric] = round(value - base_value, 4)
    return {"primary": primary, "baseline": baseline, "delta_primary_minus_baseline": deltas}


def render_markdown(comparison: Dict[str, Any]) -> str:
    primary = comparison["primary"]
    baseline = comparison["baseline"]
    delta = comparison["delta_primary_minus_baseline"]
    keys = [
        "top1_accuracy", "top5_recall", "mrr", "unresolved_precision",
        "unresolved_recall", "minority_evidence_retention", "contradiction_rejection",
        "average_candidates_evaluated", "average_patterns_checked",
    ]
    lines = [
        "# PLM-C0 v0.2 Evaluation Report",
        "",
        f"Dataset cases: **{primary['case_count']}**",
        "",
        "| Metric | PLM-C0 v0.2 | Positive lexical baseline | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in keys:
        p = primary["metrics"].get(key)
        b = baseline["metrics"].get(key)
        d = delta.get(key)
        lines.append(f"| {key} | {p} | {b} | {d} |")
    lines.extend([
        "",
        "## Definitions",
        "",
        "- Top-1 uses the final selected Concept, including `UNRESOLVED`.",
        "- Top-5 and MRR rank only a gold Concept with observable positive signal; an unsupported zero-score row does not count.",
        "- For an expected `UNRESOLVED`, rank is 1 only when the model abstains.",
        "- Minority evidence retention is Top-5 retention on cases tagged `minority_evidence`.",
        "- Contradiction rejection requires the selected Concept not to be one of the case's explicitly forbidden Concepts.",
        "- Candidates evaluated counts all Concepts scored in the target domain. Patterns checked counts configured lexical/context rules visited.",
        "",
        "## Errors",
        "",
    ])
    errors = [row for row in primary["cases"] if not row["top1_correct"]]
    if errors:
        for row in errors:
            lines.append(f"- `{row['id']}`: expected `{row['expected']}`, predicted `{row['predicted']}`")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)
