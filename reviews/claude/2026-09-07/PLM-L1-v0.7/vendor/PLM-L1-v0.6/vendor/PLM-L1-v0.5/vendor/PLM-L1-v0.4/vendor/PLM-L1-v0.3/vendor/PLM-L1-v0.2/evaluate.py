"""Frozen pair-learning evaluation. Never called by inference or training."""
import argparse
import hashlib
import json
from pathlib import Path
from plm_l1_v02.compat import ROOT, digest, generator
from plm_l1_v02.training import fit
from plm_l1_v02.bridge import translate
from evaluation_support import load_data, transform, marker_map, rename_text, LookupReader, interpret, INVALID, GOALS


def verify_freeze():
    from release_tools import source_files
    manifest = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != {p.relative_to(ROOT).as_posix() for p in source_files()}:
        raise ValueError("frozen source inventory changed")
    for name, expected in manifest["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen source changed: " + name)
    return digest(manifest)


def one(seed, dimension, condition, split, frozen):
    lexicon = load_data("lexicon")
    train, vocabulary = transform(load_data("train"), lexicon, condition)
    evaluation, _ = transform(load_data(split), lexicon, condition)
    if condition == "negative_examples_withheld":
        train = [r for r in train if r["meaning"]["polarity"] == "polarity:positive"]
    reader = fit(train, vocabulary, seed=seed, dimension=dimension, pair_learning=condition != "no_pair_learning", ordered=condition != "no_order")
    counts = dict(inputs=0, accepted=0, meaning_exact=0, wrong_meaning=0, output_requests=0,
                  generated_exact=0, wrong_generation=0, invalid_requests=len(INVALID), invalid_accepted=0,
                  negative_inputs=0, negative_accepted=0, positive_inputs=0, positive_exact=0)
    records = []
    for row in evaluation:
        counts["inputs"] += 1
        counts["output_requests"] += 2
        negative = row["meaning"]["polarity"] == "polarity:negative"
        counts["negative_inputs" if negative else "positive_inputs"] += 1
        reading = reader.read(row["text"])
        record = {"input": row["text"], "expected": row["meaning"], "read_status": reading["status"], "reason": reading["reason"], "outputs": []}
        if reading["status"] == "read":
            counts["accepted"] += 1
            counts["negative_accepted"] += int(negative)
            recovered = reader.recover(reading["packet"])
            record["recovered"] = recovered.get("slots")
            if recovered["status"] == "recovered":
                correct = recovered["slots"] == row["meaning"]
                counts["meaning_exact" if correct else "wrong_meaning"] += 1
                counts["positive_exact"] += int(correct and not negative)
            bridged = translate(reader, reading["packet"], frozen)
            if bridged["status"] == "bridged":
                for goal in GOALS:
                    out = frozen.generate(bridged["packet"], goal)
                    correct = out["status"] == "generated" and interpret(out["text"]) == row["meaning"]
                    counts["generated_exact"] += int(correct)
                    counts["wrong_generation"] += int(out["status"] == "generated" and not correct)
                    record["outputs"].append({"goal": goal, "status": out["status"], "text": out.get("text"), "meaning_exact": correct})
        records.append(record)
    invalid = []
    for text in INVALID:
        if condition == "markers_renamed":
            text = rename_text(text, marker_map(lexicon))
        result = reader.read(text)
        counts["invalid_accepted"] += int(result["status"] == "read")
        invalid.append({"text": text, "status": result["status"], "reason": result["reason"]})
    return {"seed": seed, "dimension": dimension, "condition": condition, "counts": counts,
            "reader_fingerprint": reader.fingerprint, "generator_fingerprint": frozen.fingerprint,
            "statistics": reader.meta["statistics"], "reader_trace_supervision": reader.meta["reader_trace_supervision"],
            "training_pairs": reader.meta["pair_count"], "training_digest": reader.meta["pairs_digest"],
            "records": records, "invalid_records": invalid}, reader


def references(split, frozen):
    evaluation = load_data(split)
    lookup = LookupReader(load_data("train"), load_data("lexicon"))
    rows = []
    for name in ("pair_ordinary_lookup", "fixed_v01_trace_reader"):
        exact, wrong, accepted = 0, 0, 0
        for row in evaluation:
            if name == "pair_ordinary_lookup":
                predicted = lookup.read(row["text"])
            else:
                read = frozen.read(row["text"])
                predicted = frozen.recover(read["packet"])["slots"] if read["status"] == "read" else None
            if predicted is not None:
                accepted += 1
                exact += int(predicted == row["meaning"])
                wrong += int(predicted != row["meaning"])
        invalid_accepts = sum(lookup.read(text) is not None if name == "pair_ordinary_lookup" else frozen.read(text)["status"] == "read" for text in INVALID)
        rows.append({"name": name, "inputs": len(evaluation), "accepted": accepted, "exact": exact, "wrong": wrong,
                     "invalid_requests": len(INVALID), "invalid_accepted": invalid_accepts,
                     "note": "One fixed reference run, not repeated independent seeds or an efficiency benchmark."})
    return rows


def judge(rows, protocol):
    checks = []
    gate = protocol["gates"]
    for seed in protocol["evaluation_seeds"]:
        variants = {r["condition"]: r for r in rows if r["seed"] == seed}
        full = variants["full"]["counts"]
        rate = full["generated_exact"] / full["output_requests"]
        values = {
            "full_meaning": full["meaning_exact"] / full["inputs"] >= gate["minimum_full_read_exact"],
            "full_generation": rate >= gate["minimum_full_generate_exact"],
            "full_wrong": full["wrong_meaning"] + full["wrong_generation"] <= gate["maximum_full_wrong"],
            "full_invalid": full["invalid_accepted"] <= gate["maximum_full_invalid_accepts"],
            "reader_trace_removed": variants["full"]["reader_trace_supervision"] is False,
        }
        for variant in ("no_pair_learning", "no_order"):
            c = variants[variant]["counts"]
            values[variant + "_drop"] = rate - c["generated_exact"] / c["output_requests"] >= gate["minimum_ablation_generation_drop"]
        for variant in ("roles_swapped", "states_flipped", "markers_renamed"):
            c = variants[variant]["counts"]
            values[variant] = c["meaning_exact"] / c["inputs"] >= gate["minimum_counterfactual_exact"] and c["generated_exact"] / c["output_requests"] >= gate["minimum_counterfactual_exact"] and c["wrong_meaning"] + c["wrong_generation"] <= gate["maximum_counterfactual_wrong"]
        c = variants["negative_examples_withheld"]["counts"]
        values["withheld_negative_abstention"] = c["negative_accepted"] <= gate["maximum_withheld_negative_accepts"]
        values["retained_positive_reading"] = c["positive_exact"] / c["positive_inputs"] >= gate["minimum_retained_positive_read_exact"]
        checks.extend({"seed": seed, "name": key, "passed": bool(value)} for key, value in values.items())
    checks.append({"seed": "all", "name": "fixed_generator_identical", "passed": len({r["generator_fingerprint"] for r in rows}) == 1})
    return checks


def report(output, result):
    result["result_digest"] = digest(result)
    (output / "EVALUATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    totals = {}
    for row in result["results"]:
        total = totals.setdefault(row["condition"], {k: 0 for k in row["counts"]})
        for k, value in row["counts"].items():
            total[k] += value
    lines = ["# PLM-L1 v0.2 評価結果", "", "読解手順の教師ラベルを使わず、文・意味対から構文型と役割位置・状態の対応を学習する限定実証。", "",
             "| 条件 | 意味一致 / 入力 | 意味保持生成 / 要求 | 誤意味 / 誤生成 | 範囲外入力受理 / 試行 |", "|---|---:|---:|---:|---:|"]
    for name, c in totals.items():
        lines.append(f"| {name} | {c['meaning_exact']}/{c['inputs']} | {c['generated_exact']}/{c['output_requests']} | {c['wrong_meaning']}/{c['wrong_generation']} | {c['invalid_accepted']}/{c['invalid_requests']} |")
    lines += ["", "roles_swapped/states_flippedは人工的に意味教師を変えた対照であり、通常の日本語意味への正答率ではありません。markers_renamedは助詞・語尾等を無意味記号へ置換した対照です。",
              "", "negative_examples_withheldでは否定文を学習から除去。全入力を分母に残すため、未学習の否定文を保留した分は成功率を下げます。",
              "", f"事前受入：{sum(x['passed'] for x in result['checks'])}/{len(result['checks'])}。{'合格' if result['passed'] else '開発中または未達'}。",
              "", "## 参考比較（各192文、固定1回）", "", "| 方式 | 意味一致 / 入力 | 誤り | 範囲外受理 / 試行 |", "|---|---:|---:|---:|"]
    for row in result["references"]:
        lines.append(f"| {row['name']} | {row['exact']}/{row['inputs']} | {row['wrong']} | {row['invalid_accepted']}/{row['invalid_requests']} |")
    lines += ["", "通常の表引き方式も同じ文・意味対と同じ抽象化を使います。同じ教師情報という比較であり、同じメモリbyte数や速度・省エネルギー性の比較ではありません。v0.1側は従来の読解手順教師を受けた固定モデルです。",
              "", "## 低次元ストレス（合否の対象外）", "", "| seed | 次元 | 意味一致 / 入力 | 誤意味 | 生成一致 / 要求 | 誤生成 | 範囲外受理 / 試行 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in result["stress"]:
        c = row["counts"]
        lines.append(f"| {row['seed']} | {row['dimension']} | {c['meaning_exact']}/{c['inputs']} | {c['wrong_meaning']} | {c['generated_exact']}/{c['output_requests']} | {c['wrong_generation']} | {c['invalid_accepted']}/{c['invalid_requests']} |")
    lines += ["", "次元を下げた場合の誤り・保留を隠さず記録しています。負荷に応じた閾値の学習は今回の実装範囲外です。",
              "", "## 解釈と限界", "", "学習576文、開発192文、評価192文はv0.1の組合せ分割を再利用。評価192文は新読解器の学習に未使用ですが、プロジェクトとして初見のコーパスではありません。8seedは符号の反復で、8つの独立コーパスではありません。",
              "", "生成器のコード・重みはv0.1の固定版を使用し、新しい読解の意味信号を相関で回復して旧符号へ再結合します。生成器に原文・正解意味・新読解の教師情報は渡しません。",
              "", "既知の内容語の意味ID・語種と、5スロットの意味スキーマは事前知識です。内容語を語種へ置換した既出構文型ごとの対応を学ぶ方式であり、未知構文の帰納や語義の自律獲得ではありません。教師文法から作った人工データで、独立人手評価は未実施です。",
              "", "Phase/VSA領域の言語処理であり、全演算がチップ領域の通信SSで動くという主張ではありません。R1推論・Concept更新・S1同期受信器統合は行いません。",
              "", f"結果digest：`{result['result_digest']}`", f"ソース固定digest：`{result['freeze_hash']}`", ""]
    (output / "EVALUATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise ValueError("fresh output directory required")
    freeze = "development_not_frozen" if args.development else verify_freeze()
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    frozen = generator()
    split = "development" if args.development else "evaluation"
    seeds = protocol["development_seeds"] if args.development else protocol["evaluation_seeds"]
    results = []
    for seed in seeds:
        for condition in protocol["conditions"]:
            row, reader = one(seed, protocol["dimension"], condition, split, frozen)
            results.append(row)
            print(json.dumps({"seed": seed, "condition": condition, **row["counts"]}), flush=True)
            if seed == seeds[0] and condition == "full":
                reader.save(output / "reader")
    stress = []
    if not args.development:
        for seed in protocol["stress"]["seeds"]:
            for dimension in protocol["stress"]["dimensions"]:
                row, _ = one(seed, dimension, "full", split, frozen)
                stress.append(row)
                print(json.dumps({"stress": seed, "dimension": dimension, **row["counts"]}), flush=True)
    checks = [] if args.development else judge(results, protocol)
    result = {"schema": "plm-l1-v02-results-v1", "freeze_hash": freeze, "results": results, "references": references(split, frozen),
              "stress": stress, "checks": checks, "passed": bool(checks) and all(c["passed"] for c in checks)}
    report(output, result)
    print("RESULT_DIGEST " + result["result_digest"], flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
