"""Small-sample monotone calibration; labels are read only from calibration split."""
from collections import defaultdict
from hashlib import sha256
import json


def fit_isotonic(rows):
    """Beta(1,1) per signal level, then pooled-adjacent-violators regression."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["signal"]].append(int(row["correct"]))
    blocks = []
    for signal, outcomes in sorted(grouped.items()):
        blocks.append({"upper_signal": signal, "successes": sum(outcomes) + 1.,
                       "weight": len(outcomes) + 2., "samples": len(outcomes)})
        while len(blocks) >= 2 and blocks[-2]["successes"] / blocks[-2]["weight"] > blocks[-1]["successes"] / blocks[-1]["weight"]:
            right, left = blocks.pop(), blocks.pop()
            blocks.append({"upper_signal": right["upper_signal"],
                           "successes": left["successes"] + right["successes"],
                           "weight": left["weight"] + right["weight"], "samples": left["samples"] + right["samples"]})
    return [{"upper_signal": b["upper_signal"], "probability": round(b["successes"] / b["weight"], 4),
             "samples": b["samples"], "smoothing_weight": b["weight"] - b["samples"]} for b in blocks]


def fit_calibration(data_path):
    from .engine import C2Config, PLMC2Engine
    cases = json.loads(data_path.read_text(encoding="utf-8"))["cases"]
    if any(c["split"] != "calibration" for c in cases):
        raise ValueError("Only calibration split may be used to fit confidence")
    engine = PLMC2Engine(config=C2Config(use_empirical_calibration=False))
    rows = []
    for case in cases:
        selection = engine.analyze(case["inputs"])["selections"][case["domain"]]
        rows.append({"id": case["id"], "signal": selection["reliability_signal"],
                     "correct": selection["selected"] == case["expected"], "expected": case["expected"],
                     "predicted": selection["selected"]})
    return {"method": "beta_smoothed_isotonic", "confidence_target": "selected-label correctness including UNRESOLVED",
            "data_sha256": sha256(data_path.read_bytes()).hexdigest(), "sample_count": len(rows),
            "independent_authorship": False, "external_validation": False,
            "bins": fit_isotonic(rows), "fit_rows": rows}
