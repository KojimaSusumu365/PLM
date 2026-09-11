"""Seed-separated numerical evaluation with explicit failures, abstention and ablations."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
from .core import PhaseCodebook, DecodePolicy, encode, decode, channel, digest, canonical, require
from .fixtures import make_frames, entity_candidates

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))


def summarize(rows):
    positives = [r for r in rows if r["test_kind"] == "present"]
    negatives = [r for r in rows if r["test_kind"] != "present"]
    correct = sum(r["outcome"] == "correct" for r in positives)
    wrong = sum(r["outcome"] == "wrong" for r in positives)
    abstained = sum(r["outcome"] == "abstained" for r in positives)
    false_accept = sum(r["outcome"] == "false_accept" for r in negatives)
    return {"positive_queries": len(positives), "correct": correct, "wrong": wrong, "abstained": abstained,
            "recovery_rate": correct / len(positives) if positives else None,
            "accepted_accuracy": correct / (correct + wrong) if correct + wrong else None,
            "negative_queries": len(negatives), "false_accepts": false_accept,
            "false_accept_rate": false_accept / len(negatives) if negatives else None}


def run_trial(dimension, seed, condition, *, bind_roles=True, bind_events=True):
    book = PhaseCodebook(dimension, "experiment-" + str(seed))
    frames = make_frames(condition["events"])
    candidates = entity_candidates(PROTOCOL["candidate_count"])
    memory = encode(frames, book, bind_roles=bind_roles, bind_events=bind_events)
    values, mask = channel(memory, seed=seed + dimension, **{k: condition[k] for k in ("keep_fraction", "noise_std", "phase_offset", "jitter_std")})
    policy = DecodePolicy(**PROTOCOL["policy"])
    rows = []
    for frame in frames[:PROTOCOL["query_events_per_trial"]]:
        for role in ("subject", "object"):
            truth = frame["slots"][role]
            for kind in ("present", "absent_event", "true_value_not_in_dictionary"):
                event = "absent-" + frame["event_id"] if kind == "absent_event" else frame["event_id"]
                choices = [c for c in candidates if c != truth] if kind == "true_value_not_in_dictionary" else candidates
                result = decode(values, book, frame["document_id"], event, role, choices, mask=mask,
                                policy=policy, bind_roles=bind_roles, bind_events=bind_events)
                if kind == "present":
                    outcome = "correct" if result["selected"] == truth else "abstained" if result["selected"] is None else "wrong"
                else:
                    outcome = "false_accept" if result["selected"] is not None else "correct_rejection"
                rows.append({"dimension": dimension, "seed": seed, "condition": condition["name"],
                             "event_id": event, "role": role, "test_kind": kind, "outcome": outcome,
                             "observed_components": result["observed_components"], "reason": result["reason"],
                             "selected": result["selected"], "top_score": result["top_candidates"][0]["score"] if result["top_candidates"] else None,
                             "margin": result["margin"]})
    return rows


def structural_ablations():
    book = PhaseCodebook(2048, "structural-ablations-v1")
    frames = make_frames(1)
    swapped = deepcopy(frames)
    swapped[0]["slots"]["subject"], swapped[0]["slots"]["object"] = swapped[0]["slots"]["object"], swapped[0]["slots"]["subject"]
    normal_a, normal_b = encode(frames, book), encode(swapped, book)
    bag_a, bag_b = encode(frames, book, bind_roles=False), encode(swapped, book, bind_roles=False)
    multi = make_frames(2)
    moved = deepcopy(multi)
    moved[0]["slots"], moved[1]["slots"] = moved[1]["slots"], moved[0]["slots"]
    no_event_a, no_event_b = encode(multi, book, bind_events=False), encode(moved, book, bind_events=False)
    full_a, full_b = encode(multi, book), encode(moved, book)
    return {"roleless_swap_signal_equal": bool(np.allclose(bag_a, bag_b, atol=1e-12)),
            "full_role_swap_signal_distinct": not bool(np.allclose(normal_a, normal_b, atol=1e-12)),
            "eventless_assignment_swap_signal_equal": bool(np.allclose(no_event_a, no_event_b, atol=1e-12)),
            "full_event_assignment_signal_distinct": not bool(np.allclose(full_a, full_b, atol=1e-12)),
            "meaning": "exact structural ambiguity controls; not an independent semantic benchmark"}


def run_suite(split="evaluation"):
    require(split in {"development", "evaluation"}, "Invalid split")
    require(not set(PROTOCOL["development_seeds"]) & set(PROTOCOL["evaluation_seeds"]), "Seed leakage")
    rows = []
    for dimension in PROTOCOL["dimensions"]:
        for condition in PROTOCOL["conditions"]:
            for seed in PROTOCOL[split + "_seeds"]:
                rows.extend(run_trial(dimension, seed, condition))
    conditions = []
    for dimension in PROTOCOL["dimensions"]:
        for condition in PROTOCOL["conditions"]:
            selected = [r for r in rows if r["dimension"] == dimension and r["condition"] == condition["name"]]
            conditions.append(dict(dimension=dimension, **condition, **summarize(selected)))
    lookup = {(c["dimension"], c["name"]): c for c in conditions}
    nominal, masked = lookup[(2048, "nominal")], lookup[(2048, "masked_noise")]
    ablations = structural_ablations()
    acceptance = {"nominal_all_recovered": nominal["recovery_rate"] == 1.0,
                  "nominal_no_false_accepts": nominal["false_accepts"] == 0,
                  "masked_recovery_at_least_95pct": masked["recovery_rate"] >= PROTOCOL["minimum_masked_recovery_rate"],
                  "masked_false_accept_at_most_2pct": masked["false_accept_rate"] <= PROTOCOL["maximum_masked_false_accept_rate"],
                  "no_observation_always_abstains": all(r["selected"] is None for r in rows if r["condition"] == "no_observation"),
                  "role_and_event_binding_controls": all(v for v in ablations.values() if isinstance(v, bool))}
    return {"version": "PLM-P1 v0.1", "split": split, "protocol_hash": digest(PROTOCOL),
            "numpy_version": np.__version__, "dataset_kind": "internal_synthetic_not_independent",
            "seeds": PROTOCOL[split + "_seeds"], "policy": asdict(DecodePolicy(**PROTOCOL["policy"])),
            "decoder_inputs": ["mixed_samples", "observed_mask", "codebook", "known_document_event_role_key", "candidate_dictionary"],
            "decoder_has_gold_slot_map": False, "phase_synchronization_implemented": False,
            "inference_enabled": False, "ss_demodulation_implemented": False,
            "conditions": conditions, "structural_ablations": ablations, "acceptance": acceptance,
            "acceptance_passed": all(acceptance.values()), "rows": rows}


def render_report(result):
    lines = ["# PLM-P1 v0.1 数値実証結果", "", "分割: " + result["split"], "",
             "人工的に定義した構造の符号化・回復試験です。独立意味評価・SS復調・物理回路の実証ではありません。",
             "以下の数値表は主体/対象slotの回復です。全Relationの完全一致率ではありません。状態・訂正対象は別の単体/連携試験で確認します。",
             "回復には既知の文書/出来事/役割キーと候補辞書を使います。正解の役割対応表は復号器に渡しません。", "",
             "| 次元 | 条件 | 観測率 | 回復（正解/全問） | 誤回復 | 保留 | 負例の誤受理 |", "|---:|---|---:|---:|---:|---:|---:|"]
    for c in result["conditions"]:
        lines.append(f"| {c['dimension']} | {c['name']} | {c['keep_fraction']:.1%} | {c['correct']}/{c['positive_queries']} | {c['wrong']} | {c['abstained']} | {c['false_accepts']}/{c['negative_queries']} |")
    lines += ["", "受入チェック: " + str(sum(result["acceptance"].values())) + "/" + str(len(result["acceptance"])) + "。", "",
              "受入範囲は2048次元・4出来事（28結合）のnominal/masked_noiseです。higher_load/overloadは性能保証範囲外で、誤回復・誤受理も隠さず報告します。",
              "unreferenced_quarter_turnは外部位相基準がない90度回転。S1で同期を実装する必要性を調べる失敗側試験です。",
              "負例は存在しない出来事と、正解が候補辞書にない場合。観測不足で全保留する条件を高精度と読まないでください。", "",
              "## 解釈上の限界", "",
              "相関値は確率ではなく、雑音下で閾値超えの誤回復も発生します。無条件の安全な復号は主張しません。",
              "固定閾値は工学的初期設定で未校正。異なる乱数seedは用いていますが、生成方式・評価設計の作者は共通です。",
              "候補数96、限定した次数・雑音条件の実証です。Conceptの意味的近さ・階層共有成分・未知Concept獲得は未実装。", ""]
    return "\n".join(lines)
