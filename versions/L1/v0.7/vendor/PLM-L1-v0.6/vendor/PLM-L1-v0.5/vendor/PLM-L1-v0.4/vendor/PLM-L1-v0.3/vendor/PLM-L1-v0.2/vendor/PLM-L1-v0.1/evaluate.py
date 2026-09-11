"""Frozen held-out experiment, including ablations and non-gating stress."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from plm_l1.algebra import Book, learn, digest
from plm_l1.training import fit
from plm_l1.teacher import examples, GOALS
from plm_l1.oracle import interpret, INVALID
from plm_l1.runtime import chip_roundtrip

ROOT = Path(__file__).resolve().parent


def verify_freeze():
    from release_tools import source_files
    manifest = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != {p.relative_to(ROOT).as_posix() for p in source_files()}:
        raise ValueError("source inventory changed")
    for name, expected in manifest["files"].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("frozen source changed: " + name)
    return digest(manifest)


def one_condition(seed, dimension, condition, split):
    model = fit(seed, dimension, learning=condition != "no_learning", order_binding=condition != "no_order", role_binding=condition != "no_roles")
    counts = dict(examples=0, parse_accepted=0, meaning_exact=0, wrong_meaning=0, generation_attempts=0,
                  generation_exact=0, wrong_generation=0, reordered_attempts=0, reordered_exact=0,
                  invalid_attempts=len(INVALID), invalid_accepted=0, chip_attempts=0, chip_exact=0)
    records = []
    maximum_chip_error = 0.
    for index, example in enumerate(examples(split)):
        counts["examples"] += 1
        counts["generation_attempts"] += len(GOALS)
        counts["reordered_attempts"] += 1
        reading = model.read(example["text"])
        record = {"id": example["id"], "read_status": reading["status"], "reason": reading["reason"], "outputs": []}
        if reading["status"] == "read":
            counts["parse_accepted"] += 1
            recovered = model.recover(reading["packet"])
            record["meaning_status"] = recovered["status"]
            record["recovered_slots"] = recovered.get("slots")
            if recovered["status"] == "recovered":
                correct = recovered["slots"] == example["slots"]
                counts["meaning_exact" if correct else "wrong_meaning"] += 1
            for goal in GOALS:
                generated = model.generate(reading["packet"], goal)
                correct = generated["status"] == "generated" and interpret(generated["text"]) == example["slots"]
                if correct:
                    counts["generation_exact"] += 1
                elif generated["status"] == "generated":
                    counts["wrong_generation"] += 1
                if goal != example["order"] and correct and generated["text"] != example["text"]:
                    counts["reordered_exact"] += 1
                record["outputs"].append({"goal": goal, "status": generated["status"], "text": generated.get("text"), "meaning_exact": correct})
            if condition == "full" and index < 16:
                counts["chip_attempts"] += 1
                packet, audit = chip_roundtrip(model, reading["packet"])
                maximum_chip_error = max(maximum_chip_error, audit["maximum_error"])
                out = model.generate(packet)
                counts["chip_exact"] += int(out["status"] == "generated" and interpret(out["text"]) == example["slots"])
        records.append(record)
    invalid_records = []
    for text in INVALID:
        reading = model.read(text)
        accepted = reading["status"] == "read"
        counts["invalid_accepted"] += int(accepted)
        invalid_records.append({"text": text, "status": reading["status"], "reason": reading["reason"]})
    result = {"seed": seed, "condition": condition, "counts": counts, "maximum_chip_error": maximum_chip_error,
              "model_fingerprint": model.fingerprint, "training_digest": model.meta["training_digest"],
              "memory_statistics": model.meta["memory_statistics"],
              "records_digest": digest(records), "invalid_records": invalid_records}
    result["records"] = records
    return result, model


def memory_stress(protocol):
    rows = []
    for seed in protocol["seeds"]:
        for dimension in protocol["dimensions"]:
            for count in protocol["association_counts"]:
                book = Book(dimension, seed)
                pairs = [([("stress_key", str(i))], "item:" + str(i)) for i in range(count)]
                memory, _ = learn(book, pairs)
                row = {"seed": seed, "dimension": dimension, "stored": count, "known": min(count, protocol["known_queries_max"]),
                       "unknown": protocol["unknown_queries"], "correct": 0, "wrong": 0, "abstain": 0, "false_accept": 0}
                for parts, target in pairs[:row["known"]]:
                    value = memory.recall(parts)["value"]
                    row["abstain" if value is None else "correct" if value == target else "wrong"] += 1
                for i in range(row["unknown"]):
                    row["false_accept"] += int(memory.recall([("stress_key", "missing:" + str(i))])["value"] is not None)
                rows.append(row)
    return rows


def judge(results, protocol):
    checks = []
    gates = protocol["gates"]
    for seed in protocol["evaluation_seeds"]:
        conditions = {row["condition"]: row for row in results if row["seed"] == seed}
        full = conditions["full"]
        c = full["counts"]
        rate = c["generation_exact"] / c["generation_attempts"]
        values = {
            "meaning_exact": c["meaning_exact"] / c["examples"] >= gates["minimum_full_meaning_exact_rate_per_seed"],
            "generation_exact": rate >= gates["minimum_full_generation_exact_rate_per_seed"],
            "wrong_meanings": c["wrong_meaning"] <= gates["maximum_full_wrong_meanings_per_seed"],
            "wrong_generations": c["wrong_generation"] <= gates["maximum_full_wrong_generations_per_seed"],
            "invalid_accepts": c["invalid_accepted"] <= gates["maximum_full_invalid_accepts_per_seed"],
            "reordered_exact": c["reordered_exact"] / c["reordered_attempts"] >= gates["minimum_reordered_exact_rate_per_seed"],
            "chip_error": full["maximum_chip_error"] <= gates["maximum_ideal_chip_error"],
            "chip_semantics": c["chip_attempts"] == c["chip_exact"] and c["chip_attempts"] > 0,
        }
        for condition in ("no_learning", "no_order", "no_roles"):
            ablated = conditions[condition]["counts"]
            values[condition + "_drop"] = rate - ablated["generation_exact"] / ablated["generation_attempts"] >= gates["minimum_generation_drop_each_ablation"]
        checks += [{"seed": seed, "name": name, "passed": bool(passed)} for name, passed in values.items()]
    return checks


def report(output, results, stress, checks, freeze_hash):
    summary = {"schema": "plm-l1-results-v1", "freeze_hash": freeze_hash, "results": results, "stress": stress,
               "checks": checks, "passed": bool(checks) and all(x["passed"] for x in checks)}
    summary["result_digest"] = digest(summary)
    (output / "EVALUATION.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    totals = {}
    for row in results:
        total = totals.setdefault(row["condition"], {k: 0 for k in row["counts"]})
        for k, v in row["counts"].items():
            total[k] += v
    lines = ["# PLM-L1 v0.1 評価結果", "", "人工的な限定日本語・教師付き有限状態モデルの結果。自然文の独立人手評価ではありません。", "",
             "| 方式 | 意味完全一致 / 入力 | 意味保持生成 / 試行 | 誤生成 | 語順変更成功 / 試行 | 範囲外入力の受理 / 試行 |", "|---|---:|---:|---:|---:|---:|"]
    for name, c in totals.items():
        lines.append(f"| {name} | {c['meaning_exact']}/{c['examples']} | {c['generation_exact']}/{c['generation_attempts']} | {c['wrong_generation']} | {c['reordered_exact']}/{c['reordered_attempts']} | {c['invalid_accepted']}/{c['invalid_attempts']} |")
    lines += ["", f"事前固定チェック：{sum(x['passed'] for x in checks)}/{len(checks)}。判定：{'合格' if summary['passed'] else '未達あり'}。",
              "", "学習無効は全連想記憶をゼロ化、順序無効は状態・位置キーを除外して同じ教師データで再学習、役割無効は意味信号の役割結合を除外します。候補語彙・次元・閾値は維持します。保留も全試行の分母に含めます。",
              "", "これらは内部演算の必要性を示す比較であり、従来の有限状態機械より高速・高精度であることを示す比較ではありません。",
              "", "## 記憶容量ストレス（受入条件外）", "", "言語系とは別の原子的な連想記憶に対する試験です。文書容量の評価ではありません。", "",
              "| seed | 次元 | 保存対応数 | 正回復 / 既知照会 | 誤回復 | 保留 | 未知キー誤受理 / 照会 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in stress:
        lines.append(f"| {row['seed']} | {row['dimension']} | {row['stored']} | {row['correct']}/{row['known']} | {row['wrong']} | {row['abstain']} | {row['false_accept']}/{row['unknown']} |")
    lines += ["", "容量超過での誤回復・誤受理があればそのまま記録しています。言語系の安全な保留を無制限の負荷へ一般化しません。",
              "", "## 接続と限界", "", "4チップ/成分の明示的な均衡±1列による無雑音往復を各seedの先頭16入力で検査。S1 v0.2の受信器・パイロット同期を統合した実験ではありません。",
              "", "単一出来事・6固有名・4動詞・2語順・否定/仮定の4状態に限定。教師用の文法と状態注釈は手設計。自然な文体の改善、語義・構文の自律獲得、長文、一般推論、真偽判定は未実施です。",
              "", "相関は確率ではありません。生成する断定形は入力の表現形式を保ったものであり、現実の事実を検証したことを意味しません。",
              "", f"結果digest: `{summary['result_digest']}`", f"ソース固定digest: `{freeze_hash}`", ""]
    (output / "EVALUATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise ValueError("output directory already exists")
    freeze_hash = "development_not_frozen" if args.development else verify_freeze()
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    results = []
    seeds = protocol["development_seeds"] if args.development else protocol["evaluation_seeds"]
    for seed in seeds:
        for condition in protocol["conditions"]:
            result, model = one_condition(seed, protocol["dimension"], condition, "development" if args.development else "evaluation")
            results.append(result)
            print(json.dumps({"seed": seed, "condition": condition, **result["counts"]}), flush=True)
            if seed == seeds[0] and condition == "full":
                model.save(output / "model")
    stress = [] if args.development else memory_stress(protocol["stress"])
    checks = [] if args.development else judge(results, protocol)
    summary = report(output, results, stress, checks, freeze_hash)
    print("RESULT_DIGEST " + summary["result_digest"], flush=True)
    return 0 if args.development or summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
