"""Separate standalone writer and fixed-reader integration evaluation."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from plm_l1_v03.algebra import canonical, digest
from plm_l1_v03.training import fit
from plm_l1_v03.features import GOALS, ROLES
from plm_l1_v03.bridge import fixed_reader, translate
from evaluation_support import ROOT, data, oracle, transform, score, LookupWriter


def source_files():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".md", ".txt")]
    for folder in ("plm_l1_v03", "tests", "evaluation", "data", "vendor"):
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file())
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix != ".pyc")


def verify_freeze():
    manifest = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    actual = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    if actual != manifest["files"]:
        raise ValueError("frozen source changed")
    return digest(manifest)


def bad_packets(writer, meaning):
    packet = writer.encode(meaning)
    result = [dict(packet, text="hidden source"), dict(packet, meaning=meaning), dict(packet, writer_fingerprint="bad"),
              dict(packet, dimension=128 if writer.book.dimension != 128 else 512), dict(packet, eligible_for_inference=True),
              dict(packet, real=[0.] * writer.book.dimension, imag=[0.] * writer.book.dimension)]
    for value in (float("nan"), float("inf"), True, "1", 1e100):
        p = copy.deepcopy(packet)
        p["real"][0] = value
        result.append(p)
    noise = writer.book.code("probe_noise", "unrelated")
    result.append(dict(packet, real=(np.array(packet["real"]) + noise.real).tolist(), imag=(np.array(packet["imag"]) + noise.imag).tolist()))
    return result


def one(seed, dimension, condition, split, reader, interpretor, invalid, patterns):
    train, lexicon = transform(data("train"), data("lexicon"), condition)
    if condition == "negative_examples_withheld":
        train = [r for r in train if r["meaning"]["polarity"] == "polarity:positive"]
    writer = fit(train, lexicon, seed=seed, dimension=dimension, pair_learning=condition != "no_pair_learning",
                 use_prefix=condition != "no_prefix", use_status=condition != "no_status")
    evaluation, _ = transform(data(split), data("lexicon"), condition)
    unique = {canonical(r["meaning"]): r["meaning"] for r in evaluation}
    counts = {k: 0 for k in ("standalone_requests", "standalone_generated", "standalone_exact", "standalone_wrong",
              "roundtrip_requests", "roundtrip_generated", "roundtrip_exact", "roundtrip_wrong", "reader_inputs", "reader_exact",
              "negative_requests", "negative_generated", "positive_requests", "positive_exact", "invalid_texts", "invalid_texts_accepted",
              "invalid_packets", "invalid_packets_generated")}
    records = []

    def record(mode, meaning, goal, out, source=None):
        counts[mode + "_requests"] += 1
        generated = out["status"] == "generated"
        scored = score(out.get("text"), meaning, goal, condition, interpretor, patterns)
        exact = generated and scored["meaning_exact"] and scored["goal_exact"]
        counts[mode + "_generated"] += int(generated)
        counts[mode + "_exact"] += int(exact)
        counts[mode + "_wrong"] += int(generated and not exact)
        if mode == "standalone":
            negative = meaning["polarity"] == "polarity:negative"
            counts["negative_requests" if negative else "positive_requests"] += 1
            counts["negative_generated"] += int(negative and generated)
            counts["positive_exact"] += int(not negative and exact)
        records.append({"mode": mode, "source_for_evaluator_only": source, "expected": meaning, "goal": goal,
                        "status": out["status"], "text": out.get("text"), "reason": out.get("reason"), **scored})

    # Standalone path: gold meaning is explicit input by definition. No reader.
    for key in sorted(unique):
        meaning = unique[key]
        packet = writer.encode(meaning)
        for goal in GOALS:
            record("standalone", meaning, goal, writer.generate(packet, goal))
    # Integrated path: only a recovered fixed-reader signal is bridged. Gold
    # semantic labels are used exclusively below for scoring, never encoding.
    for row in data(split):
        counts["reader_inputs"] += 1
        read = reader.read(row["text"])
        bridged = {"status": "abstain", "reason": "reader_abstained"}
        if read["status"] == "read":
            recovered = reader.recover(read["packet"])
            counts["reader_exact"] += int(recovered.get("slots") == row["meaning"])
            bridged = translate(reader, read["packet"], writer)
        for goal in GOALS:
            out = writer.generate(bridged["packet"], goal) if bridged["status"] == "bridged" else {"status": "abstain", "reason": bridged["reason"]}
            record("roundtrip", row["meaning"], goal, out, row["text"])
    for text in invalid:
        counts["invalid_texts"] += 1
        counts["invalid_texts_accepted"] += int(reader.read(text)["status"] == "read")
    for packet in bad_packets(writer, next(iter(unique.values()))):
        counts["invalid_packets"] += 1
        counts["invalid_packets_generated"] += int(writer.generate(packet)["status"] == "generated")
    return {"seed": seed, "dimension": dimension, "condition": condition, "counts": counts, "records": records,
            "writer_fingerprint": writer.fingerprint, "reader_fingerprint": reader.fingerprint,
            "training_pairs": len(train), "statistics": writer.meta["statistics"],
            "supplied_trace_supervision": writer.meta["supplied_trace_supervision"]}, writer


def references(split, interpretor, patterns):
    lookup = LookupWriter(data("train"), data("lexicon"))
    from plm_l1_v02.compat import generator
    legacy = generator()
    meanings = {canonical(r["meaning"]): r["meaning"] for r in data(split)}
    result = []
    for name in ("ordinary_lookup_writer", "fixed_v01_trace_writer"):
        counts = {"requests": 0, "exact": 0, "wrong": 0}
        for key in sorted(meanings):
            meaning = meanings[key]
            for goal in GOALS:
                if name == "ordinary_lookup_writer":
                    text = lookup.generate(meaning, goal)
                else:
                    vector = sum(legacy.book.code("semantic_role", r) * legacy.book.code("value", meaning[r]) for r in ROLES)
                    text = legacy.generate(legacy.pack(vector), goal + "_first").get("text")
                s = score(text, meaning, goal, "full", interpretor, patterns)
                exact = s["meaning_exact"] and s["goal_exact"]
                counts["requests"] += 1
                counts["exact"] += int(exact)
                counts["wrong"] += int(text is not None and not exact)
        result.append({"name": name, **counts})
    return result


def judge(results, protocol):
    checks = []
    for seed in protocol["evaluation_seeds"]:
        rows = {r["condition"]: r for r in results if r["seed"] == seed}
        full = rows["full"]["counts"]
        values = {"standalone_exact": full["standalone_exact"] / full["standalone_requests"] >= .98,
                  "roundtrip_exact": full["roundtrip_exact"] / full["roundtrip_requests"] >= .98,
                  "no_wrong_output": full["standalone_wrong"] + full["roundtrip_wrong"] == 0,
                  "reader_exact": full["reader_inputs"] == full["reader_exact"],
                  "no_trace_supervision": rows["full"]["supplied_trace_supervision"] is False,
                  "invalid_boundaries": full["invalid_texts_accepted"] + full["invalid_packets_generated"] == 0}
        base = full["standalone_exact"] / full["standalone_requests"]
        for name in ("no_pair_learning", "no_prefix", "no_status"):
            c = rows[name]["counts"]
            values[name + "_drop"] = base - c["standalone_exact"] / c["standalone_requests"] >= .50
        for name in ("roles_swapped", "states_flipped", "markers_renamed"):
            c = rows[name]["counts"]
            values[name] = all(c[m + "_exact"] / c[m + "_requests"] >= .98 and c[m + "_wrong"] == 0 for m in ("standalone", "roundtrip"))
        c = rows["negative_examples_withheld"]["counts"]
        values["withheld_negative"] = c["negative_generated"] == 0
        values["retained_positive"] = c["positive_exact"] / c["positive_requests"] >= .98
        checks.extend({"seed": seed, "name": name, "passed": bool(value)} for name, value in values.items())
    checks.append({"seed": "all", "name": "reader_fixed", "passed": len({r["reader_fingerprint"] for r in results}) == 1})
    return checks


def report(output, result):
    result["result_digest"] = digest(result)
    (output / "EVALUATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    totals = {}
    for row in result["results"]:
        count = totals.setdefault(row["condition"], {k: 0 for k in row["counts"]})
        for k, v in row["counts"].items():
            count[k] += v
    lines = ["# PLM-L1 v0.3 評価結果", "", "生成単体と固定v0.2読解器との接続を分離して採点。意味と指定した先頭役割の両方が一致した場合のみ成功。", "",
             "| 条件 | 生成単体 一致/要求 | 読解→生成 一致/要求 | 単体/接続の誤生成 | 不正信号から生成/試行 |", "|---|---:|---:|---:|---:|"]
    for name, c in totals.items():
        lines.append(f"| {name} | {c['standalone_exact']}/{c['standalone_requests']} | {c['roundtrip_exact']}/{c['roundtrip_requests']} | {c['standalone_wrong']}/{c['roundtrip_wrong']} | {c['invalid_packets_generated']}/{c['invalid_packets']} |")
    lines += ["", f"事前受入：{sum(c['passed'] for c in result['checks'])}/{len(result['checks'])}、判定：{result['passed']}。",
              "", "roles_swapped/states_flippedは教師の意味対応を人工変更した対照。通常の日本語意味の正答率ではない。接続でも生成器の人工的対応に対して採点しており、自然文の意味保持を主張するのはfull条件だけ。markers_renamedは生成側の記号を置換し、読解側は元の日本語入力のまま固定。",
              "", "negative_examples_withheldは否定を学習から除去し、要求分母には残す。未知の否定意味・目標を保留した分は成功に数えない。",
              "", "## 参考方式", "", "| 方式 | 正解/要求 | 誤生成 |", "|---|---:|---:|"]
    for row in result["references"]:
        lines.append(f"| {row['name']} | {row['exact']}/{row['requests']} | {row['wrong']} |")
    lines += ["", "表引きは同じ対・初期語彙・自動対応付け・prefix設計を使い、数値符号は使わない。v0.1は従来の手順教師を使った固定生成器。各1回の単体比較で、同じメモリbyte数・速度・エネルギー予算の比較ではない。",
              "", "## 低次元ストレス（非合否）", "", "| seed | 次元 | 単体 一致/要求 | 接続 一致/要求 | 単体/接続の誤生成 | 不正信号から生成/試行 |", "|---|---:|---:|---:|---:|---:|"]
    for row in result["stress"]:
        c = row["counts"]
        lines.append(f"| {row['seed']} | {row['dimension']} | {c['standalone_exact']}/{c['standalone_requests']} | {c['roundtrip_exact']}/{c['roundtrip_requests']} | {c['standalone_wrong']}/{c['roundtrip_wrong']} | {c['invalid_packets_generated']}/{c['invalid_packets']} |")
    lines += ["", "## 解釈と制約", "", "訓練576文、開発192文、評価192文はv0.1/v0.2の分割を再利用。評価のユニーク意味は96個。単体は96意味×2目標、接続は192入力文×2目標。8seedは符号の反復であり、新しい独立コーパスではない。",
              "", "学習APIには文章と意味を与え、正解の操作列や状態列を別途与えない。訓練文章と意味から語役割と次の抽象出力記号を内部で導出する。初期語義・語種・5スロット・copy/literal/endという出力設計・prefix特徴は手設計。すべての知識を自律獲得したわけではない。",
              "", "生成時は自分の出力prefixを用いる。評価正解prefix、原文、全文検索、旧生成器へのフォールバックはない。文型prefixの学習であり未知構文の自律帰納ではない。学習時に曖昧な語対応は拒否する。",
              "", "固定v0.2読解器と新生成器は別々の数値記憶・コードブックを使う。橋渡しは回復意味の再結合。R1推論・Concept更新・S1同期統合なし。Phase/VSA演算であり全演算の明示チップSS化ではない。負荷適応型の閾値は未実装。",
              "", f"結果digest：`{result['result_digest']}`", "", f"ソース固定digest：`{result['freeze_hash']}`", ""]
    (output / "EVALUATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise ValueError("fresh output required")
    freeze = "development_not_frozen" if args.development else verify_freeze()
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    reader = fixed_reader()
    interpretor, invalid, patterns = oracle()
    split = "development" if args.development else "evaluation"
    seeds = protocol["development_seeds"] if args.development else protocol["evaluation_seeds"]
    rows, stress = [], []
    for seed in seeds:
        for condition in protocol["conditions"]:
            row, writer = one(seed, protocol["dimension"], condition, split, reader, interpretor, invalid, patterns)
            rows.append(row)
            print(json.dumps({"seed": seed, "condition": condition, **row["counts"]}), flush=True)
            if seed == seeds[0] and condition == "full":
                writer.save(output / "writer")
    if not args.development:
        for seed in protocol["stress_seeds"]:
            for dimension in protocol["stress_dimensions"]:
                row, _ = one(seed, dimension, "full", split, reader, interpretor, invalid, patterns)
                stress.append(row)
                print(json.dumps({"stress": seed, "dimension": dimension, **row["counts"]}), flush=True)
    checks = [] if args.development else judge(rows, protocol)
    result = {"schema": "plm-l1-v03-evaluation-v1", "freeze_hash": freeze, "results": rows, "stress": stress,
              "references": references(split, interpretor, patterns), "checks": checks,
              "passed": bool(checks) and all(c["passed"] for c in checks)}
    report(output, result)
    print("RESULT_DIGEST " + result["result_digest"], flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
