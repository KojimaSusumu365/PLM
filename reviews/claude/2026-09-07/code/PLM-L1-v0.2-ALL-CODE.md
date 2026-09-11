# PLM-L1-v0.2 全コード（当該版直下・vendor重複除外）

原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。

## `evaluate.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/evaluate.py`  
SHA256: `916034a24dce9dcab10d42f07b498961230b58a6a3e25ce56c3a4bfd16df4624`

````python
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
````

## `evaluation_support.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/evaluation_support.py`  
SHA256: `95dc962fe3e33baca4e6d1c79728edfe59c719c677602f372f5fad5d887f57ee`

````python
"""Evaluator-only controls and non-SS lookup reference; not imported by learner."""
import copy
import json
from collections import Counter
from plm_l1_v02.compat import ROOT, canonical
from plm_l1_v02.features import tokenize, abstract, descriptor
from plm_l1_v02.training import observations
from plm_l1.oracle import interpret, INVALID

GOALS = ("subject_first", "object_first")


def load_data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def marker_map(lexicon):
    markers = sorted(t["surface"] for t in lexicon["tokens"] if t["kind"] == "marker")
    return {surface: f"~M{i}~" for i, surface in enumerate(markers)}


def rename_text(text, mapping):
    for surface in sorted(mapping, key=lambda x: (-len(x), x)):
        text = text.replace(surface, mapping[surface])
    return text


def transform(pairs, lexicon, condition):
    rows, vocab = copy.deepcopy(pairs), copy.deepcopy(lexicon)
    if condition == "roles_swapped":
        for row in rows:
            m = row["meaning"]
            m["subject"], m["object"] = m["object"], m["subject"]
    elif condition == "states_flipped":
        for row in rows:
            m = row["meaning"]
            m["polarity"] = "polarity:negative" if m["polarity"] == "polarity:positive" else "polarity:positive"
            m["modality"] = "modality:asserted" if m["modality"] == "modality:hypothetical" else "modality:hypothetical"
    elif condition == "markers_renamed":
        mapping = marker_map(lexicon)
        for row in rows:
            row["text"] = rename_text(row["text"], mapping)
        for token in vocab["tokens"]:
            if token["kind"] == "marker":
                token["surface"] = mapping[token["surface"]]
    return rows, vocab


class LookupReader:
    """Same automatically derived correspondences, ordinary table representation.

    This is a control, not a fallback used by the SS reader. Equal supervision,
    not equal byte footprint or a speed/energy benchmark.
    """
    def __init__(self, pairs, lexicon):
        rows = observations(pairs, lexicon)
        self.tables = {}
        for name, values in rows.items():
            groups = {}
            for key, target in values:
                groups.setdefault(canonical(key), Counter())[target] += 1
            self.tables[name] = {}
            for key, counts in groups.items():
                best = counts.most_common(1)[0]
                self.tables[name][key] = best[0] if best[1] / counts.total() >= .65 else None
        self.kinds = {t["surface"]: t["kind"] for t in lexicon["tokens"]}
        self.values = {t["surface"]: t["value"] for t in lexicon["tokens"]}

    def read(self, text):
        try:
            tokens = tokenize(text, self.kinds)
        except ValueError:
            return None
        shape = abstract(tokens, self.kinds)
        if self.tables["support"].get(canonical(descriptor(shape))) != "supported":
            return None
        slots = {}
        for position, token in enumerate(tokens):
            kind = self.kinds[token]
            if kind == "marker":
                continue
            role = self.tables["roles"].get(canonical(descriptor(shape, position=position, kind=kind)))
            if role not in ("subject", "object", "predicate") or role in slots:
                return None
            slots[role] = self.values[token]
        for slot in ("polarity", "modality"):
            value = self.tables["states"].get(canonical(descriptor(shape, slot=slot)))
            if value is None:
                return None
            slots[slot] = value
        return slots if len(slots) == 5 else None
````

## `plm_l1_v02/__init__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/__init__.py`  
SHA256: `2ec29b98d58c783ed58cee1f47dfc70d439c2fa77e377a6f6764adbb8aa9f176`

````python
"""PLM-L1 v0.2: sentence/meaning-pair supervised phase reader."""
__version__ = "0.2.0"
````

## `plm_l1_v02/__main__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/__main__.py`  
SHA256: `5a0936fac58f23fd3ae75ccd9c09193d115a7485e979f918d672026ecd80fa66`

````python
import argparse
import json
from pathlib import Path
from .runtime import PairReader
from .compat import generator
from .bridge import generate, translate


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="SS pair-trained controlled-language reader")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--pairs", required=True)
    train.add_argument("--lexicon", required=True)
    train.add_argument("--seed", default="pair-development-0")
    train.add_argument("--out", required=True)
    read = commands.add_parser("read")
    read.add_argument("--model", required=True)
    read.add_argument("--text", required=True)
    read.add_argument("--out", required=True)
    for name in ("generate", "bridge"):
        command = commands.add_parser(name)
        command.add_argument("--model", required=True)
        command.add_argument("--packet", required=True)
        if name == "generate":
            command.add_argument("--goal", default="object_first")
        else:
            command.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "train":
        from .training import fit
        model = fit(read_json(args.pairs), read_json(args.lexicon), seed=args.seed)
        model.save(args.out)
        result = {"status": "trained", "reader_fingerprint": model.fingerprint, "statistics": model.meta["statistics"],
                  "reader_trace_supervision": False, "supervision_fields": ["text", "meaning"]}
    else:
        model = PairReader.load(args.model)
        if args.command == "read":
            result = model.read(args.text)
            if result["status"] == "read":
                write_new(args.out, result.pop("packet"))
        elif args.command == "bridge":
            result = translate(model, read_json(args.packet), generator())
            if result["status"] == "bridged":
                write_new(args.out, result.pop("packet"))
        else:
            result = generate(model, read_json(args.packet), generator(), args.goal)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "abstain" else 0


if __name__ == "__main__":
    raise SystemExit(main())
````

## `plm_l1_v02/bridge.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/bridge.py`  
SHA256: `a139cac5da64093639d2f6a9657f4fbdbe4486a32aee3cd1a658b85bfd6b81a3`

````python
"""Numerical meaning-code bridge into the frozen v0.1 generator.

The bridge recovers the new reader's signal, then rebinds the selected symbols
using the fixed generator codebook. No text, gold, teacher traces or grammar
decisions are supplied to the generator.
"""
import numpy as np
from .runtime import ROLES, abstain


def translate(reader, packet, frozen_generator):
    recovered = reader.recover(packet)
    if recovered["status"] != "recovered":
        return abstain(recovered["reason"], packet=None)
    vector = np.zeros(frozen_generator.book.dimension, dtype=np.complex128)
    for role in ROLES:
        value = recovered["slots"][role]
        if value not in frozen_generator.meta["slot_candidates"][role]:
            return abstain("unsupported_generator_vocabulary", packet=None)
        vector += frozen_generator.role(role) * frozen_generator.book.code("value", value)
    return {"status": "bridged", "packet": frozen_generator.pack(vector), "eligible_for_inference": False}


def generate(reader, packet, frozen_generator, goal="object_first"):
    bridged = translate(reader, packet, frozen_generator)
    if bridged["status"] != "bridged":
        return abstain(bridged["reason"], text=None)
    return frozen_generator.generate(bridged["packet"], goal)
````

## `plm_l1_v02/compat.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/compat.py`  
SHA256: `5500c372bf82ec0a2617a645356d02466cf5cf234f9eec258b2487f59add519e`

````python
"""Use byte-preserved v0.1 phase primitives and a fixed generation model."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "PLM-L1-v0.1"
if str(VENDOR) not in sys.path:
    # Keep the calling release's scripts ahead of similarly named v0.1 scripts.
    sys.path.insert(1, str(VENDOR))
from plm_l1.algebra import Book, Memory, learn, canonical, digest, require
from plm_l1.runtime import Model as LegacyModel


def generator():
    return LegacyModel.load(VENDOR / "results" / "model")
````

## `plm_l1_v02/features.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/features.py`  
SHA256: `622b624d666bd76bfb45f8929ca4237a99c307aed236c6bdbefb99a70ad65165`

````python
"""Language-neutral token abstraction and ordered phasor composition.

Known lexical kinds are prior knowledge. No particle, suffix, polarity or
grammar-state meanings occur here. Whole abstract shapes are learned, not
unbounded syntax induction.
"""
import numpy as np
from .compat import canonical, require


def validate_lexicon(lexicon):
    require(type(lexicon) is dict and set(lexicon) == {"tokens", "slot_candidates"}, "invalid lexicon fields")
    require(set(lexicon["slot_candidates"]) == {"subject", "object", "predicate", "polarity", "modality"}, "invalid roles")
    seen = set()
    for token in lexicon["tokens"]:
        require(type(token) is dict and set(token) == {"surface", "kind", "value"}, "invalid lexical fields")
        require(type(token["surface"]) is str and 0 < len(token["surface"]) <= 32 and token["surface"] not in seen, "invalid/duplicate surface")
        require(token["kind"] in ("entity", "predicate", "marker"), "unsupported lexical kind")
        if token["kind"] == "marker":
            require(token["value"] is None, "markers must not carry semantic supervision")
        else:
            require(type(token["value"]) is str and token["value"].startswith(token["kind"] + ":"), "invalid lexical value")
        seen.add(token["surface"])
    for role, candidates in lexicon["slot_candidates"].items():
        require(type(candidates) is list and len(candidates) >= 2 and len(set(candidates)) == len(candidates), "invalid candidate inventory")
        require(all(type(x) is str and x for x in candidates), "invalid candidates")


def tokenize(text, kinds):
    require(type(text) is str and 0 < len(text) <= 256, "empty_or_oversized_input")
    vocabulary = sorted(kinds, key=lambda s: (-len(s), s))
    tokens, offset = [], 0
    while offset < len(text):
        surface = next((s for s in vocabulary if text.startswith(s, offset)), None)
        require(surface is not None, "unknown_token")
        tokens.append(surface)
        require(len(tokens) <= 9, "token_capacity_exceeded")
        offset += len(surface)
    return tokens


def abstract(tokens, kinds):
    return [["kind", kinds[t]] if kinds[t] != "marker" else ["surface", t] for t in tokens]


def descriptor(shape, *, position=None, kind=None, slot=None, ordered=True):
    # Ablation merges exact key identities as well as removing permutations.
    shape = shape if ordered else sorted(shape, key=canonical)
    result = {"shape": shape}
    if position is not None:
        result["position"] = position if ordered else 0
        result["kind"] = kind
    if slot is not None:
        result["slot"] = slot
    return result


class Space:
    def __init__(self, book, ordered=True):
        self.book, self.ordered = book, ordered
        self.cache = {}

    def key(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            shape_key = canonical(description["shape"])
            cache_key = "shape:" + shape_key
            if cache_key not in self.cache:
                value = np.ones(self.book.dimension, dtype=np.complex128)
                for position, token in enumerate(description["shape"]):
                    value *= np.roll(self.book.code("abstract_token", token), 17 * position if self.ordered else 0)
                self.cache[cache_key] = value
            value = self.cache[cache_key].copy()
            for field in ("position", "kind", "slot"):
                if field in description:
                    value *= self.book.code("query_" + field, description[field])
            self.cache[identity] = value
        return self.cache[identity]
````

## `plm_l1_v02/memory.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/memory.py`  
SHA256: `0c3f737a935bd1ab30bc029963467f1e789a7c5fab15ff85ae179f32c1ec4381`

````python
"""Balanced Hebbian phase association using compositional sequence keys."""
import numpy as np
from .compat import canonical, require


class Association:
    def __init__(self, space, vector, candidates, minimum=.65, margin=.25):
        self.space = space
        self.vector = np.asarray(vector, dtype=np.complex128).copy()
        require(self.vector.shape == (space.book.dimension,) and np.isfinite(self.vector).all(), "invalid association weights")
        self.candidates = tuple(sorted(set(candidates)))
        require(bool(self.candidates), "empty association candidates")
        self.basis = np.array([space.book.code("value", c).conj() for c in self.candidates])
        self.minimum, self.margin = minimum, margin
        self.cache = {}

    def recall(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            query = self.vector * self.space.key(description)
            scores = np.real(self.basis @ query) / self.space.book.dimension
            order = np.argsort(-scores, kind="stable")
            top = float(scores[order[0]])
            runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
            accepted = top >= self.minimum and top - runner >= self.margin
            self.cache[identity] = {"value": self.candidates[order[0]] if accepted else None,
                                    "score": round(top, 8), "margin": round(top - runner, 8)}
        return dict(self.cache[identity])


def fit_association(space, observations, enabled=True):
    groups, candidates = {}, set()
    for description, target in observations:
        identity = canonical(description)
        if identity not in groups:
            groups[identity] = [description, {}]
        counts = groups[identity][1]
        counts[target] = counts.get(target, 0) + 1
        candidates.add(target)
    require(bool(groups), "empty paired observations")
    require(len(groups) <= 256, "association_context_capacity_exceeded")
    vector = np.zeros(space.book.dimension, dtype=np.complex128)
    if enabled:
        for identity in sorted(groups):
            description, counts = groups[identity]
            total = sum(counts.values())
            mean_value = sum(space.book.code("value", label) * (count / total) for label, count in sorted(counts.items()))
            vector += space.key(description).conj() * mean_value
    stats = {"contexts": len(groups), "observations": len(observations),
             "conflicting_contexts": sum(len(row[1]) > 1 for row in groups.values())}
    return Association(space, vector, candidates), stats
````

## `plm_l1_v02/runtime.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/runtime.py`  
SHA256: `214f09ea490328606762a31323ab081ce66bbec254ca53e188667cb947a9161c`

````python
"""Pair-trained reader; no teacher states, operations or language-specific rules."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .compat import Book, Memory, canonical, digest, require
from .features import tokenize, abstract, descriptor, Space
from .memory import Association

ROLES = ("subject", "object", "predicate", "polarity", "modality")
ASSOCIATIONS = ("support", "roles", "states")


def abstain(reason, **extra):
    return dict(status="abstain", reason=reason, eligible_for_inference=False, **extra)


class PairReader:
    def __init__(self, metadata, memories, lexical):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-pair-reader-v1" and self.meta.get("eligible_for_inference") is False, "invalid reader metadata")
        require(set(memories) == set(ASSOCIATIONS), "invalid reader memory inventory")
        require(set(self.meta["slot_candidates"]) == set(ROLES), "invalid slot inventory")
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.space = Space(self.book, self.meta["ordered"])
        self.memories, self.lexical = memories, lexical
        all_memories = dict(memories, lexical=lexical)
        for memory in all_memories.values():
            require(memory.vector.shape == (self.book.dimension,), "weight dimension mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {
            name: {"hash": hashlib.sha256(memory.vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(memory.candidates)}
            for name, memory in sorted(all_memories.items())}})
        self.slot_basis = {r: np.array([self.book.code("value", value).conj() for value in self.meta["slot_candidates"][r]]) for r in ROLES}

    def query(self, name, shape, **kwargs):
        return self.memories[name].recall(descriptor(shape, ordered=self.meta["ordered"], **kwargs))

    def pack(self, vector):
        return {"schema": "plm-l1-pair-meaning-v1", "reader_fingerprint": self.fingerprint,
                "dimension": self.book.dimension, "real": vector.real.tolist(), "imag": vector.imag.tolist(),
                "eligible_for_inference": False}

    def unpack(self, packet):
        require(type(packet) is dict and set(packet) == {"schema", "reader_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
        require(packet["schema"] == "plm-l1-pair-meaning-v1" and packet["reader_fingerprint"] == self.fingerprint, "packet_reader_mismatch")
        require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension and packet["eligible_for_inference"] is False, "invalid_packet_contract")
        for field in ("real", "imag"):
            require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(x) in (int, float) for x in packet[field]), "invalid_signal_values")
        values = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
        require(np.isfinite(values).all() and np.max(np.abs(values)) <= 32., "nonfinite_or_excessive_signal")
        return values

    def read(self, text):
        try:
            tokens = tokenize(text, self.meta["token_kinds"])
        except ValueError as error:
            return abstain(str(error), packet=None)
        shape = abstract(tokens, self.meta["token_kinds"])
        support = self.query("support", shape)
        if support["value"] != "supported":
            return abstain("unsupported_or_ambiguous_shape", packet=None, audit={"support": support})
        vector = np.zeros(self.book.dimension, dtype=np.complex128)
        slots, audit = {}, {"support": support, "roles": [], "states": {}}
        for position, token in enumerate(tokens):
            kind = self.meta["token_kinds"][token]
            if kind == "marker":
                continue
            content = self.lexical.recall([("token", token)])
            selected = self.query("roles", shape, position=position, kind=kind)
            role = selected["value"]
            audit["roles"].append({"position": position, "role": selected, "content": content})
            if role not in ("subject", "object", "predicate") or content["value"] is None:
                return abstain("role_or_lexical_association_unresolved", packet=None, audit=audit)
            if role in slots or content["value"] not in self.meta["slot_candidates"][role]:
                return abstain("duplicate_or_invalid_role", packet=None, audit=audit)
            slots[role] = content["value"]
        if set(slots) != {"subject", "object", "predicate"}:
            return abstain("incomplete_content", packet=None, audit=audit)
        for slot in ("polarity", "modality"):
            selected = self.query("states", shape, slot=slot)
            audit["states"][slot] = selected
            if selected["value"] not in self.meta["slot_candidates"][slot]:
                return abstain("semantic_status_unresolved", packet=None, audit=audit)
            slots[slot] = selected["value"]
        for role in ROLES:
            vector += self.book.code("semantic_role", role) * self.book.code("value", slots[role])
        return {"status": "read", "reason": "pair_learned_observation", "packet": self.pack(vector), "audit": audit, "eligible_for_inference": False}

    def recover(self, packet):
        try:
            vector = self.unpack(packet)
        except (ValueError, TypeError, OverflowError) as error:
            return abstain(str(error), slots=None)
        slots, audit = {}, {}
        clean = np.zeros(self.book.dimension, dtype=np.complex128)
        for role in ROLES:
            scores = np.real(self.slot_basis[role] @ (vector * self.book.code("semantic_role", role).conj())) / self.book.dimension
            order = np.argsort(-scores, kind="stable")
            top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
            audit[role] = {"score": round(top, 8), "margin": round(top - runner, 8)}
            if top < self.meta["minimum"] or top - runner < self.meta["margin"]:
                return abstain("ambiguous_meaning", slots=None, audit=audit)
            slots[role] = self.meta["slot_candidates"][role][order[0]]
            clean += self.book.code("semantic_role", role) * self.book.code("value", slots[role])
        residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
        if residual > .20:
            return abstain("meaning_residual_excessive", slots=None, audit=audit)
        return {"status": "recovered", "slots": slots, "audit": audit, "residual": round(residual, 8), "eligible_for_inference": False}

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "reader.json").exists() and not (target / "weights.npz").exists(), "reader_output_exists")
        all_memories = dict(self.memories, lexical=self.lexical)
        info = {"metadata": self.meta, "fingerprint": self.fingerprint,
                "candidates": {name: list(memory.candidates) for name, memory in all_memories.items()}}
        with (target / "reader.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        np.savez_compressed(target / "weights.npz", **{name: memory.vector for name, memory in all_memories.items()})

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "reader.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "candidates"}, "invalid reader envelope")
        meta = info["metadata"]
        book = Book(meta["dimension"], meta["seed"])
        space = Space(book, meta["ordered"])
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            require(set(weights.files) == set(ASSOCIATIONS) | {"lexical"}, "invalid weight names")
            memories = {name: Association(space, weights[name], info["candidates"][name], meta["minimum"], meta["margin"]) for name in ASSOCIATIONS}
            lexical = Memory(book, weights["lexical"], info["candidates"]["lexical"])
        reader = cls(meta, memories, lexical)
        require(reader.fingerprint == info["fingerprint"], "reader_hash_mismatch")
        return reader
````

## `plm_l1_v02/training.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/plm_l1_v02/training.py`  
SHA256: `7a7af7d87c1f720d61b6a717a48ded53417fedb51754050d9cbba267a7a2a1a2`

````python
"""Strict sentence/meaning-pair reader training.

No teacher, oracle, reader trace, generator, or state/action label API is imported.
Alignment uses ONLY an explicitly supplied initial content lexicon and gold slot
values in each training pair. This remains supervised and lexically grounded.
"""
from .compat import Book, learn, canonical, digest, require
from .features import validate_lexicon, tokenize, abstract, descriptor, Space
from .memory import fit_association
from .runtime import PairReader


def observations(pairs, lexicon, ordered=True):
    validate_lexicon(lexicon)
    require(type(pairs) is list and 0 < len(pairs) <= 10000, "invalid pair collection")
    kinds = {t["surface"]: t["kind"] for t in lexicon["tokens"]}
    lexical = {t["surface"]: t["value"] for t in lexicon["tokens"] if t["value"] is not None}
    output = {"support": [], "roles": [], "states": []}
    meanings_by_text = {}
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"text", "meaning"}, "pairs accept only text and meaning; trace/order/state/action fields prohibited")
        meaning = pair["meaning"]
        require(type(meaning) is dict and set(meaning) == set(lexicon["slot_candidates"]), "invalid meaning fields")
        for role, value in meaning.items():
            require(value in lexicon["slot_candidates"][role], "meaning outside public candidates")
        tokens = tokenize(pair["text"], kinds)
        identity = pair["text"]
        require(identity not in meanings_by_text or meanings_by_text[identity] == canonical(meaning), "contradictory duplicate text")
        meanings_by_text[identity] = canonical(meaning)
        shape = abstract(tokens, kinds)
        output["support"].append((descriptor(shape, ordered=ordered), "supported"))
        # Derive token-role alignments from equality of lexical IDs and supplied
        # semantic values; no step-by-step parse labels or particle rules.
        aligned_positions = set()
        for role in ("subject", "object", "predicate"):
            positions = [i for i, token in enumerate(tokens) if lexical.get(token) == meaning[role]]
            require(len(positions) == 1, "ambiguous_or_missing_lexical_alignment")
            position = positions[0]
            require(position not in aligned_positions, "nonunique_role_alignment")
            aligned_positions.add(position)
            output["roles"].append((descriptor(shape, position=position, kind=kinds[tokens[position]], ordered=ordered), role))
        require(aligned_positions == {i for i, token in enumerate(tokens) if kinds[token] != "marker"}, "unexplained_content_token")
        for slot in ("polarity", "modality"):
            output["states"].append((descriptor(shape, slot=slot, ordered=ordered), meaning[slot]))
    return output


def fit(pairs, lexicon, *, seed="pair-development-0", dimension=8192, pair_learning=True, ordered=True):
    require(type(pair_learning) is bool and type(ordered) is bool, "invalid ablation switches")
    rows = observations(pairs, lexicon, ordered)
    book = Book(dimension, seed)
    space = Space(book, ordered)
    memories, statistics = {}, {}
    for name in rows:
        memories[name], statistics[name] = fit_association(space, rows[name], pair_learning)
    lexical_pairs = [([("token", t["surface"])], t["value"]) for t in lexicon["tokens"] if t["value"] is not None]
    lexical, lexical_stats = learn(book, lexical_pairs)
    metadata = {"schema": "plm-l1-pair-reader-v1", "seed": seed, "dimension": dimension,
                "ordered": ordered, "pair_learning": pair_learning,
                "token_kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]},
                "slot_candidates": lexicon["slot_candidates"], "lexicon_digest": digest(lexicon),
                "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)),
                "statistics": statistics, "lexical_prior_statistics": lexical_stats,
                "supervision_fields": ["text", "meaning"], "reader_trace_supervision": False,
                "minimum": .65, "margin": .25, "eligible_for_inference": False}
    return PairReader(metadata, memories, lexical)
````

## `prepare_data.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/prepare_data.py`  
SHA256: `01e9237d562563414d3ebd75b03234d4c806f5bf2ff91744d819de02be02565c`

````python
"""Dataset-side export ONLY. Old grammar generates fixtures, never learner labels.

The pair learner does not import this module. Trace/order/IDs are discarded.
Old reader_trace/writer_trace are not called, including during export.
"""
import json
from pathlib import Path
from plm_l1_v02.compat import ROOT, generator
from plm_l1.teacher import examples, lexicon


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    for split in ("train", "development", "evaluation"):
        pairs = [{"text": row["text"], "meaning": row["slots"]} for row in examples(split)]
        write_new(ROOT / "data" / (split + ".json"), pairs)
    tokens = []
    for surface, category, value in lexicon():
        if surface == "<EOS>":
            continue
        kind = "entity" if value.startswith("entity:") else "predicate" if value.startswith("predicate:") else "marker"
        tokens.append({"surface": surface, "kind": kind, "value": value if kind != "marker" else None})
    write_new(ROOT / "data" / "lexicon.json", {"tokens": tokens, "slot_candidates": generator().meta["slot_candidates"]})


if __name__ == "__main__":
    main()
````

## `release_tools.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/release_tools.py`  
SHA256: `88eaa25c8bf93ea7d7987f1b722d7ec7fce57488d2b48c424f7e36453ef40092`

````python
"""Source freezing, preservation checks, demos and additive ZIP release."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from plm_l1_v02.compat import ROOT, VENDOR, digest, generator
from plm_l1_v02.runtime import PairReader
from plm_l1_v02.bridge import generate, translate


def source_files():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".md", ".txt")]
    for name in ("plm_l1_v02", "tests", "data", "evaluation", "vendor"):
        files.extend(p for p in (ROOT / name).rglob("*") if p.is_file())
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix != ".pyc")


def hashes(files, base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("baseline", "check-baseline", "freeze", "demo", "pack"))
    args = parser.parse_args()
    if args.command in ("baseline", "check-baseline"):
        files = []
        for name in ("PLM-L1-v0.1", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        manifest = {"files": hashes(files, ROOT.parent)}
        path = ROOT / "verification" / "PRESERVED_BASELINE.json"
        if args.command == "baseline":
            write_new(path, manifest)
        elif manifest != json.loads(path.read_text(encoding="utf-8")):
            raise ValueError("existing release changed")
        original = ROOT.parent / "PLM-L1-v0.1"
        a = hashes([p for p in original.rglob("*") if p.is_file()], original)
        b = hashes([p for p in VENDOR.rglob("*") if p.is_file()], VENDOR)
        if a != b:
            raise ValueError("v0.1 vendored copy changed")
        print(json.dumps({"status": "recorded" if args.command == "baseline" else "unchanged", "preserved_files": len(files), "vendor_files": len(a)}))
    elif args.command == "freeze":
        manifest = {"schema": "plm-l1-v02-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write_new(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif args.command == "demo":
        reader = PairReader.load(ROOT / "results" / "reader")
        frozen = generator()
        texts = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。", "太郎は花子を助けた。"]
        rows = []
        for text in texts:
            read = reader.read(text)
            row = {"input": text, "status": read["status"], "reason": read["reason"]}
            if read["status"] == "read":
                row["recovered"] = reader.recover(read["packet"])
                row["generated"] = generate(reader, read["packet"], frozen)
                if not rows:
                    write_new(ROOT / "examples" / "MEANING_PACKET.json", read["packet"])
                    write_new(ROOT / "examples" / "LEGACY_GENERATOR_PACKET.json", translate(reader, read["packet"], frozen)["packet"])
            rows.append(row)
        write_new(ROOT / "examples" / "ROUNDTRIPS.json", {"audience": "human/evaluator only; never a generator input", "demos": rows})
    else:
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts)
        write_new(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v02-release-v1", "files": hashes(files, ROOT)})
        archive = ROOT.parent / "PLM-L1-v0.2.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with (ROOT.parent / "PLM-L1-v0.2.sha256").open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": checksum, "files": len(files) + 1}))


if __name__ == "__main__":
    main()
````

## `requirements.txt`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/requirements.txt`  
SHA256: `7bd6b8946940b79948c548c8048e545684b91c8edc9444d8dfc0c8f76a97c0a7`

````text
numpy==2.3.5
````

## `tests/test_pairs.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/tests/test_pairs.py`  
SHA256: `1e9f9b8537d98834b61bb6d39169368546046bdf17690b6a46d8812eafc75a0a`

````python
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v02.compat import Book, generator, canonical
from plm_l1_v02.features import Space, descriptor, abstract, tokenize, validate_lexicon
from plm_l1_v02.training import fit, observations
from plm_l1_v02.runtime import PairReader
from plm_l1_v02.memory import Association
from plm_l1_v02.bridge import translate, generate
from evaluation_support import load_data, transform, marker_map, rename_text, LookupReader, interpret, INVALID


class PairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, cls.dev, cls.lex = load_data("train"), load_data("development"), load_data("lexicon")
        cls.reader, cls.gen = fit(cls.train, cls.lex), generator()
        cls.text = "太郎が花子を助けた。"
        cls.packet = cls.reader.read(cls.text)["packet"]

    def test_development_read_and_generate(self):
        for row in self.dev:
            with self.subTest(text=row["text"]):
                read = self.reader.read(row["text"])
                self.assertEqual(read["status"], "read")
                self.assertEqual(self.reader.recover(read["packet"])["slots"], row["meaning"])
                for goal in ("subject_first", "object_first"):
                    out = generate(self.reader, read["packet"], self.gen, goal)
                    self.assertEqual(out["status"], "generated")
                    self.assertEqual(interpret(out["text"]), row["meaning"])

    def test_teacher_and_old_reader_not_called(self):
        import plm_l1.teacher as teacher
        with patch.object(teacher, "reader_trace", side_effect=AssertionError("trace forbidden")), patch.object(teacher, "writer_trace", side_effect=AssertionError("writer forbidden")), patch.object(type(self.gen), "read", side_effect=AssertionError("legacy reader forbidden")):
            model = fit(self.train, self.lex)
            r = model.read(self.text)
            self.assertEqual(generate(model, r["packet"], self.gen)["status"], "generated")

    def test_training_signature(self):
        params = list(inspect.signature(fit).parameters)
        self.assertEqual(params, ["pairs", "lexicon", "seed", "dimension", "pair_learning", "ordered"])

    def test_no_trace_fields_allowed(self):
        for name in ("reader_trace", "state", "actions", "order", "gold_position", "id", "metadata"):
            row = dict(self.train[0], **{name: []})
            with self.subTest(name=name), self.assertRaises(ValueError):
                fit([row], self.lex)

    def test_no_extra_meaning_fields(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["state_trace"] = []
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_pair_schema_is_only_text_meaning(self):
        self.assertTrue(all(set(row) == {"text", "meaning"} for row in self.train))
        self.assertFalse(self.reader.meta["reader_trace_supervision"])
        self.assertEqual(self.reader.meta["supervision_fields"], ["text", "meaning"])

    def test_automatically_derived_correspondences(self):
        self.assertEqual(self.reader.meta["statistics"]["support"]["contexts"], 8)
        self.assertEqual(self.reader.meta["statistics"]["roles"]["contexts"], 24)
        self.assertEqual(self.reader.meta["statistics"]["states"]["contexts"], 16)

    def test_no_marker_semantic_labels(self):
        self.assertTrue(all(t["value"] is None for t in self.lex["tokens"] if t["kind"] == "marker"))

    def test_reject_marker_semantic_labels(self):
        lex = copy.deepcopy(self.lex)
        next(t for t in lex["tokens"] if t["kind"] == "marker")["value"] = "polarity:negative"
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_roles_follow_counterfactual_supervision(self):
        train, lex = transform(self.train, self.lex, "roles_swapped")
        model = fit(train, lex)
        expected = interpret(self.text)
        expected["subject"], expected["object"] = expected["object"], expected["subject"]
        self.assertEqual(model.recover(model.read(self.text)["packet"])["slots"], expected)

    def test_states_follow_counterfactual_supervision(self):
        train, lex = transform(self.train, self.lex, "states_flipped")
        model = fit(train, lex)
        slots = model.recover(model.read(self.text)["packet"])["slots"]
        self.assertEqual(slots["polarity"], "polarity:negative")
        self.assertEqual(slots["modality"], "modality:hypothetical")

    def test_opaque_markers_learned(self):
        train, lex = transform(self.train, self.lex, "markers_renamed")
        model = fit(train, lex)
        text = rename_text(self.text, marker_map(self.lex))
        self.assertEqual(model.recover(model.read(text)["packet"])["slots"], interpret(self.text))

    def test_removed_negative_examples_not_guessed(self):
        train = [r for r in self.train if r["meaning"]["polarity"] == "polarity:positive"]
        model = fit(train, self.lex)
        self.assertEqual(model.read("太郎が花子を助けなかった。")["status"], "abstain")
        self.assertEqual(model.read(self.text)["status"], "read")

    def test_no_pair_learning_keeps_lexicon_but_cannot_read(self):
        model = fit(self.train, self.lex, pair_learning=False)
        self.assertEqual(model.lexical.recall([("token", "太郎")])["value"], "entity:太郎")
        self.assertEqual(model.read(self.text)["status"], "abstain")

    def test_no_order_is_ambiguous(self):
        model = fit(self.train, self.lex, ordered=False)
        self.assertGreater(model.meta["statistics"]["roles"]["conflicting_contexts"], 0)
        self.assertEqual(model.read(self.text)["status"], "abstain")

    def test_state_memory_necessary(self):
        memories = dict(self.reader.memories)
        old = memories["states"]
        memories["states"] = Association(old.space, np.zeros(old.space.book.dimension), old.candidates)
        model = PairReader(self.reader.meta, memories, self.reader.lexical)
        self.assertEqual(model.read(self.text)["reason"], "semantic_status_unresolved")

    def test_role_memory_necessary(self):
        memories = dict(self.reader.memories)
        old = memories["roles"]
        memories["roles"] = Association(old.space, np.zeros(old.space.book.dimension), old.candidates)
        model = PairReader(self.reader.meta, memories, self.reader.lexical)
        self.assertEqual(model.read(self.text)["reason"], "role_or_lexical_association_unresolved")

    def test_ordered_shape_is_not_bag_of_words(self):
        kinds = self.reader.meta["token_kinds"]
        a = abstract(tokenize(self.text, kinds), kinds)
        b = abstract(tokenize("花子を太郎が助けた。", kinds), kinds)
        space = Space(Book())
        self.assertGreater(np.linalg.norm(space.key(descriptor(a)) - space.key(descriptor(b))), 1.)
        collapsed = Space(Book(), False)
        np.testing.assert_array_equal(collapsed.key(descriptor(a, ordered=False)), collapsed.key(descriptor(b, ordered=False)))

    def test_shape_abstracts_names_and_verbs(self):
        kinds = self.reader.meta["token_kinds"]
        self.assertEqual(abstract(tokenize(self.text, kinds), kinds), abstract(tokenize("次郎が美咲を褒めた。", kinds), kinds))

    def test_shapes_learned_not_preinstalled(self):
        train = [r for r in self.train if not r["text"].startswith("もし")]
        model = fit(train, self.lex)
        self.assertEqual(model.read("もし太郎が花子を助けたら。")["status"], "abstain")

    def test_paraphrases_same_meaning(self):
        other = self.reader.read("花子を太郎が助けた。")["packet"]
        np.testing.assert_allclose(self.reader.unpack(self.packet), self.reader.unpack(other), atol=1e-12)

    def test_swapped_entities_differ(self):
        other = self.reader.read("花子が太郎を助けた。")["packet"]
        self.assertGreater(np.linalg.norm(self.reader.unpack(self.packet) - self.reader.unpack(other)), 1.)

    def test_negative_hypothetical(self):
        packet = self.reader.read("もし太郎が花子を助けなかったら。")["packet"]
        out = generate(self.reader, packet, self.gen)
        self.assertEqual(out["text"], "もし花子を太郎が助けなかったら。")

    def test_self_reference_inference(self):
        read = self.reader.read("太郎が太郎を助けた。")
        self.assertEqual(read["status"], "read")
        slots = self.reader.recover(read["packet"])["slots"]
        self.assertEqual(slots["subject"], slots["object"])

    def test_ambiguous_training_alignment_rejected(self):
        row = {"text": "太郎が太郎を助けた。", "meaning": interpret("太郎が太郎を助けた。")}
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_missing_alignment_rejected(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["predicate"] = "predicate:gaze_at" if row["meaning"]["predicate"] != "predicate:gaze_at" else "predicate:help"
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_contradictory_duplicate_rejected(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["subject"], row["meaning"]["object"] = row["meaning"]["object"], row["meaning"]["subject"]
        with self.assertRaises(ValueError):
            fit([self.train[0], row], self.lex)

    def test_training_order_determinism(self):
        model = fit(list(reversed(self.train)), self.lex)
        self.assertEqual(model.fingerprint, self.reader.fingerprint)

    def test_training_no_source_sentence_in_model_metadata(self):
        serial = canonical(self.reader.meta)
        for row in self.train:
            self.assertNotIn(row["text"], serial)
        self.assertNotIn("read_action", serial)
        self.assertNotIn("read_next", serial)

    def test_invalid_inputs(self):
        for text in INVALID:
            with self.subTest(text=text):
                self.assertEqual(self.reader.read(text)["status"], "abstain")

    def test_nonstring_input(self):
        for value in (None, {}, [], True, 1):
            self.assertEqual(self.reader.read(value)["status"], "abstain")

    def test_packet_has_no_gold(self):
        self.assertEqual(set(self.packet), {"schema", "reader_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        self.assertNotIn("太郎", canonical(self.packet))

    def test_extra_packet_fields(self):
        for field in ("text", "meaning", "gold", "trace", "metadata", "order"):
            self.assertEqual(self.reader.recover(dict(self.packet, **{field: []}))["status"], "abstain")

    def test_nonfinite_packet(self):
        for value in (float("nan"), float("inf"), True, "1", 1e100):
            packet = copy.deepcopy(self.packet)
            packet["real"][0] = value
            self.assertEqual(self.reader.recover(packet)["status"], "abstain")

    def test_wrong_packet_identity(self):
        self.assertEqual(self.reader.recover(dict(self.packet, reader_fingerprint="bad"))["status"], "abstain")

    def test_wrong_packet_dimension(self):
        self.assertEqual(self.reader.recover(dict(self.packet, dimension=2))["status"], "abstain")

    def test_inference_disabled(self):
        self.assertEqual(self.reader.recover(dict(self.packet, eligible_for_inference=True))["status"], "abstain")
        self.assertFalse(self.reader.read(self.text)["eligible_for_inference"])

    def test_zero_packet(self):
        packet = self.reader.pack(np.zeros(self.reader.book.dimension, dtype=complex))
        self.assertEqual(self.reader.recover(packet)["status"], "abstain")

    def test_interference_packet(self):
        vector = self.reader.unpack(self.packet) + self.reader.book.code("noise", "unrelated")
        self.assertEqual(self.reader.recover(self.reader.pack(vector))["status"], "abstain")

    def test_bridge_no_text_or_labels(self):
        bridged = translate(self.reader, self.packet, self.gen)
        self.assertEqual(bridged["status"], "bridged")
        self.assertEqual(set(bridged["packet"]), {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        self.assertEqual(self.gen.recover(bridged["packet"])["slots"], interpret(self.text))

    def test_bridge_preserves_generator_fingerprint(self):
        before = self.gen.fingerprint
        generate(self.reader, self.packet, self.gen)
        self.assertEqual(before, self.gen.fingerprint)
        self.assertEqual(before, generator().fingerprint)

    def test_bridge_refuses_bad_signal(self):
        self.assertEqual(translate(self.reader, {}, self.gen)["status"], "abstain")

    def test_unknown_generation_goal(self):
        self.assertEqual(generate(self.reader, self.packet, self.gen, "essay")["status"], "abstain")

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as directory:
            self.reader.save(directory)
            loaded = PairReader.load(directory)
            self.assertEqual(loaded.fingerprint, self.reader.fingerprint)
            self.assertEqual(loaded.read(self.text)["packet"], self.packet)

    def test_save_overwrite_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            self.reader.save(directory)
            with self.assertRaises(ValueError):
                self.reader.save(directory)

    def test_model_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.reader.save(directory)
            path = Path(directory) / "reader.json"
            info = json.loads(path.read_text(encoding="utf-8"))
            info["metadata"]["pair_count"] += 1
            path.write_text(json.dumps(info), encoding="utf-8")
            with self.assertRaises(ValueError):
                PairReader.load(directory)

    def test_invalid_dimension(self):
        with self.assertRaises(ValueError):
            fit(self.train, self.lex, dimension=129)

    def test_empty_pairs(self):
        with self.assertRaises(ValueError):
            fit([], self.lex)

    def test_type_validation(self):
        with self.assertRaises(ValueError):
            fit(self.train, self.lex, ordered=1)

    def test_pair_partition_disjoint(self):
        keys = lambda rows: {(r["meaning"]["subject"], r["meaning"]["object"], r["meaning"]["predicate"]) for r in rows}
        a, b, c = keys(self.train), keys(self.dev), keys(load_data("evaluation"))
        self.assertFalse(a & b or a & c or b & c)

    def test_ordinary_lookup_control(self):
        model = LookupReader(self.train, self.lex)
        for row in self.dev:
            self.assertEqual(model.read(row["text"]), row["meaning"])

    def test_learner_source_does_not_import_teacher_generator_or_oracle(self):
        import plm_l1_v02.training as training
        import plm_l1_v02.runtime as runtime
        for module in (training, runtime):
            code = inspect.getsource(module)
            self.assertNotIn("import plm_l1.teacher", code)
            self.assertNotIn("from plm_l1.teacher", code)
            self.assertNotIn("from evaluation_support", code)
            self.assertNotIn("import generator", code)
            for literal in ("太郎", "花子", "もし", "なかった", '"が"', '"を"'):
                self.assertNotIn(literal, code)


if __name__ == "__main__":
    unittest.main()
````

## `verify_release.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/verify_release.py`  
SHA256: `5b635b0812e706eb31320e9aa3814d4299be963e5b1a6f27daa3ca9f173a25e7`

````python
"""Tests plus two-stage physical isolation of pair learning and fixed generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from evaluate import verify_freeze, judge
from plm_l1_v02.compat import ROOT, VENDOR, digest
from plm_l1_v02.runtime import PairReader
from evaluation_support import interpret


def run(args, cwd, output, name, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, env=env, text=True, encoding="utf-8", capture_output=True, timeout=180)
    log = result.stdout + result.stderr
    (output / (name + ".log")).write_text(log, encoding="utf-8")
    if result.returncode != expected:
        raise ValueError(name + " failed: " + log[-2000:])
    return result.stdout, log


def copy_legacy_runtime(target):
    package = target / "plm_l1"
    package.mkdir(parents=True)
    for name in ("__init__.py", "__main__.py", "algebra.py", "runtime.py"):
        shutil.copyfile(VENDOR / "plm_l1" / name, package / name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("fresh verification output required")
    output.mkdir(parents=True)
    freeze = verify_freeze()
    _, new_log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], ROOT, output, "NEW_TESTS")
    _, old_log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], VENDOR, output, "LEGACY_TESTS")
    test_counts = {"new": int(re.search(r"Ran (\d+) tests", new_log).group(1)), "v01": int(re.search(r"Ran (\d+) tests", old_log).group(1))}
    result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
    claimed = result.pop("result_digest")
    if digest(result) != claimed or result["freeze_hash"] != freeze:
        raise ValueError("saved evaluation integrity failed")
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    checks = judge(result["results"], protocol)
    if checks != result["checks"] or not all(c["passed"] for c in checks):
        raise ValueError("saved acceptance failed")
    isolated = output / "pair-only"
    (isolated / "plm_l1_v02").mkdir(parents=True)
    for source in (ROOT / "plm_l1_v02").glob("*.py"):
        shutil.copyfile(source, isolated / "plm_l1_v02" / source.name)
    isolated_vendor = isolated / "vendor" / "PLM-L1-v0.1"
    copy_legacy_runtime(isolated_vendor)
    for name in ("train.json", "lexicon.json"):
        shutil.copyfile(ROOT / "data" / name, isolated / name)
    # At this point neither teacher, evaluation files, nor ANY legacy weights
    # are present. Reader fitting must use only the supplied pair/lexicon files.
    assertion = "from pathlib import Path; from plm_l1_v02.compat import VENDOR; import importlib.util; assert not (VENDOR/'results').exists(); assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; assert not Path('evaluation.json').exists(); print('no teacher, no evaluation data, no legacy weights')"
    run(["-c", assertion], isolated, output, "PAIR_ONLY_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v02", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", protocol["evaluation_seeds"][0], "--out", "reader"], isolated, output, "PAIR_ONLY_TRAIN")
    fitted = json.loads(stdout)
    expected_reader = PairReader.load(ROOT / "results" / "reader")
    if fitted["reader_fingerprint"] != expected_reader.fingerprint:
        raise ValueError("isolated fit differs from release reader")
    # Add only fixed generator numerical weights after the training check.
    model_dir = isolated_vendor / "results" / "model"
    model_dir.mkdir(parents=True)
    for name in ("model.json", "weights.npz"):
        shutil.copyfile(VENDOR / "results" / "model" / name, model_dir / name)
    generation_only = output / "generation-only"
    copy_legacy_runtime(generation_only)
    (generation_only / "model").mkdir()
    for name in ("model.json", "weights.npz"):
        shutil.copyfile(VENDOR / "results" / "model" / name, generation_only / "model" / name)
    run(["-c", "import importlib.util; assert importlib.util.find_spec('plm_l1_v02') is None; assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; print('fixed generator only')"], generation_only, output, "GENERATOR_ONLY_BOUNDARY")
    texts = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。"]
    demos = []
    for index, text in enumerate(texts):
        own_packet = f"meaning-{index}.json"
        bridge_packet = f"legacy-{index}.json"
        run(["-m", "plm_l1_v02", "read", "--model", "reader", "--text", text, "--out", own_packet], isolated, output, f"READ_{index}")
        run(["-m", "plm_l1_v02", "bridge", "--model", "reader", "--packet", own_packet, "--out", bridge_packet], isolated, output, f"BRIDGE_{index}")
        shutil.copyfile(isolated / bridge_packet, generation_only / bridge_packet)
        stdout, _ = run(["-m", "plm_l1", "generate", "--model", "model", "--packet", bridge_packet, "--goal", "object_first"], generation_only, output, f"GENERATE_{index}")
        generated = json.loads(stdout)
        if generated["status"] != "generated" or interpret(generated["text"]) != interpret(text):
            raise ValueError("isolated generation changed meaning")
        demos.append({"input": text, "output": generated["text"], "meaning_exact": True})
    run(["-m", "plm_l1_v02", "read", "--model", "reader", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], isolated, output, "ABSTAIN", expected=2)
    if (isolated / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    manifest_checked = False
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        manifest_checked = True
    verification = {"status": "passed", "source_freeze": freeze, "result_digest": claimed,
                    "test_counts": test_counts, "acceptance_checks": len(checks),
                    "pair_only_fit_without_teacher_or_old_weights": True, "isolated_fit_fingerprint_equal": True,
                    "fixed_generator_without_new_reader": True, "isolated_roundtrips": demos,
                    "release_manifest_checked": manifest_checked, "full_numeric_rerun_in_this_command": False,
                    "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

