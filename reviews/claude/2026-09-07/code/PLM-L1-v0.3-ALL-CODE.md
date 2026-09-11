# PLM-L1-v0.3 全コード（当該版直下・vendor重複除外）

原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。

## `evaluate.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/evaluate.py`  
SHA256: `ce66f6d590b72e910dbf32b5bcdd2f39954f987e98680b17426185e93be3e7c0`

````python
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
````

## `evaluation_support.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/evaluation_support.py`  
SHA256: `5616e04ccde7f1a7c506960234d6d9fecb98de8c155e3c9ad6ec14ab28903297`

````python
"""Evaluator-only language oracle and ordinary lookup reference."""
import copy
import json
from collections import Counter
from pathlib import Path
from plm_l1_v03.algebra import canonical
from plm_l1_v03.features import aligned_examples, Space, END, CONTENT
from plm_l1_v03.bridge import fixed_reader

ROOT = Path(__file__).resolve().parent


def data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def oracle():
    # Only the evaluator loads this old independent bounded grammar.
    fixed_reader()
    from plm_l1.oracle import interpret, INVALID, PATTERNS
    return interpret, INVALID, PATTERNS


def alter_meaning(meaning, condition):
    m = dict(meaning)
    if condition == "roles_swapped":
        m["subject"], m["object"] = m["object"], m["subject"]
    if condition == "states_flipped":
        m["polarity"] = "polarity:negative" if m["polarity"] == "polarity:positive" else "polarity:positive"
        m["modality"] = "modality:asserted" if m["modality"] == "modality:hypothetical" else "modality:hypothetical"
    return m


def marker_map():
    return {s: f"~M{i}~" for i, s in enumerate(sorted(t["surface"] for t in data("lexicon")["tokens"] if t["kind"] == "marker"))}


def rename(text, mapping):
    for a in sorted(mapping, key=lambda s: (-len(s), s)):
        text = text.replace(a, mapping[a])
    return text


def transform(pairs, lexicon, condition):
    pairs, lexicon = copy.deepcopy(pairs), copy.deepcopy(lexicon)
    for row in pairs:
        row["meaning"] = alter_meaning(row["meaning"], condition)
        if condition == "markers_renamed":
            row["text"] = rename(row["text"], marker_map())
    if condition == "markers_renamed":
        mapping = marker_map()
        for token in lexicon["tokens"]:
            if token["kind"] == "marker":
                token["surface"] = mapping[token["surface"]]
    return pairs, lexicon


def score(text, meaning, goal, condition, interpretor, patterns):
    if condition == "markers_renamed" and type(text) is str:
        text = rename(text, {v: k for k, v in marker_map().items()})
    found = interpretor(text)
    if found is None:
        return {"meaning_exact": False, "goal_exact": False, "wrong_slots": list(meaning)}
    found = alter_meaning(found, condition)
    first = next(("subject" if i == 0 else "object" for i, p in enumerate(patterns) if p.fullmatch(text)), None)
    if condition == "roles_swapped":
        first = "object" if first == "subject" else "subject"
    return {"meaning_exact": found == meaning, "goal_exact": first == goal,
            "wrong_slots": [r for r in meaning if meaning[r] != found[r]]}


class LookupWriter:
    """Same pair-derived prefix targets, ordinary maps, no phase codec needed."""
    def __init__(self, pairs, lexicon):
        examples = aligned_examples(pairs, lexicon)
        self.space = Space(None)
        self.tables = {}
        for row in examples:
            for i, symbol in enumerate(row["sequence"] + [END]):
                key = canonical(self.space.context(row["meaning"], row["goal"], row["sequence"][:i]))
                self.tables.setdefault(key, Counter())[symbol] += 1
        self.lexical = {t["value"]: t["surface"] for t in lexicon["tokens"] if t["value"] is not None}

    def generate(self, meaning, goal):
        prefix, output, used = [], [], set()
        for _ in range(12):
            key = canonical(self.space.context(meaning, goal, prefix))
            candidates = self.tables.get(key)
            if not candidates or len(candidates) != 1:
                return None
            symbol = next(iter(candidates))
            if symbol == END:
                return "".join(output) if used == set(CONTENT) else None
            kind, value = json.loads(symbol)
            if kind == "slot":
                if value in used or (not used and value != goal):
                    return None
                used.add(value)
                output.append(self.lexical[meaning[value]])
            else:
                output.append(value)
            prefix.append(symbol)
        return None
````

## `plm_l1_v03/__init__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/__init__.py`  
SHA256: `26f1f030d206c44d3be768406bc3c313f6bf43683b5c6d82fb62f995c2aaa1e3`

````python
"""Sentence/meaning-pair trained phase writer, version 0.3.0."""
__version__ = "0.3.0"
````

## `plm_l1_v03/__main__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/__main__.py`  
SHA256: `aa208cd1f42ecc6b0a12a3a1edf954a1eef2a84349a87356d7d8afc21b500694`

````python
import argparse
import json
from pathlib import Path
from .runtime import Writer


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--pairs", required=True)
    train.add_argument("--lexicon", required=True)
    train.add_argument("--out", required=True)
    train.add_argument("--seed", default="writer-development-0")
    train.add_argument("--dimension", type=int, default=8192)
    for name in ("encode", "read", "generate"):
        command = sub.add_parser(name)
        command.add_argument("--model", required=True)
        if name == "generate":
            command.add_argument("--packet", required=True)
            command.add_argument("--goal", choices=("subject", "object"), default="object")
        else:
            command.add_argument("--out", required=True)
            command.add_argument("--meaning" if name == "encode" else "--text", required=True)
    args = parser.parse_args()
    try:
        if args.command == "train":
            from .training import fit
            model = fit(load(args.pairs), load(args.lexicon), seed=args.seed, dimension=args.dimension)
            model.save(args.out)
            result = {"status": "trained", "writer_fingerprint": model.fingerprint, "statistics": model.meta["statistics"]}
        else:
            model = Writer.load(args.model)
            if args.command == "generate":
                result = model.generate(load(args.packet), args.goal)
            elif args.command == "encode":
                write(args.out, model.encode(load(args.meaning)))
                result = {"status": "encoded"}
            else:
                from .bridge import fixed_reader, translate
                reader = fixed_reader()
                reading = reader.read(args.text)
                if reading["status"] == "read":
                    result = translate(reader, reading["packet"], model)
                    if result["status"] == "bridged":
                        write(args.out, result.pop("packet"))
                else:
                    result = {"status": "abstain", "reason": reading["reason"]}
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result["status"] == "abstain" else 0
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
````

## `plm_l1_v03/algebra.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/algebra.py`  
SHA256: `947ec54904c60ec7a6ea2dd7fa7ebb2ed3570e35f27461b8ee30bffbb6c19d92`

````python
"""Deterministic unit phasors and Hebbian holographic associative memory.

No linguistic rules, original sentences, or training labels are consulted here.
"""
import hashlib
import json
import numpy as np


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def require(test, message):
    if not test:
        raise ValueError(message)


class Book:
    def __init__(self, dimension=8192, seed="development-0"):
        require(type(dimension) is int and 128 <= dimension <= 16384 and dimension % 64 == 0, "invalid dimension")
        require(type(seed) is str and 0 < len(seed) <= 128, "invalid seed")
        self.dimension, self.seed = dimension, seed
        self.cache = {}

    def code(self, namespace, value):
        key = canonical(["plm-l1-phase-u53-v1", self.seed, namespace, value])
        if key not in self.cache:
            raw = hashlib.shake_256(key.encode("utf-8")).digest(8 * self.dimension)
            phase = (np.frombuffer(raw, dtype="<u8") >> 11).astype(float) * (2.0 ** -53) * (2 * np.pi)
            vector = np.exp(1j * phase)
            vector.setflags(write=False)
            self.cache[key] = vector
        return self.cache[key]

    def key(self, parts):
        out = np.ones(self.dimension, dtype=np.complex128)
        for namespace, value in parts:
            out *= self.code(namespace, value)
        return out


class Memory:
    def __init__(self, book, vector, candidates, minimum=0.60, margin=0.25):
        self.book = book
        self.vector = np.asarray(vector, dtype=np.complex128).copy()
        require(self.vector.shape == (book.dimension,) and np.isfinite(self.vector).all(), "invalid memory")
        self.candidates = tuple(sorted(set(candidates)))
        require(bool(self.candidates), "empty candidates")
        self.basis = np.array([book.code("value", c).conj() for c in self.candidates])
        self.minimum, self.margin = minimum, margin
        self.cache = {}

    def recall(self, parts):
        identity = canonical(parts)
        if identity not in self.cache:
            query = self.vector * self.book.key(parts)
            scores = np.real(self.basis @ query) / self.book.dimension
            order = np.argsort(-scores, kind="stable")
            top = float(scores[order[0]])
            runner = max(0.0, float(scores[order[1]])) if len(order) > 1 else 0.0
            accepted = top >= self.minimum and top - runner >= self.margin
            self.cache[identity] = {
                "value": self.candidates[order[0]] if accepted else None,
                "score": round(top, 8), "margin": round(top - runner, 8),
                "reason": "recovered" if accepted else "weak_or_ambiguous_association",
            }
        return dict(self.cache[identity])


def learn(book, observations, enabled=True):
    """Balanced Hebbian association: H = sum_k conj(k) * mean(v | k).

    Counts are collected only during fitting; runtime retains H and vocabulary,
    never the context->label lookup. Repetitions do not inflate memory gain.
    """
    groups, candidates = {}, set()
    for parts, target in observations:
        key = canonical(parts)
        if key not in groups:
            groups[key] = [parts, {}]
        counts = groups[key][1]
        counts[target] = counts.get(target, 0) + 1
        candidates.add(target)
    require(bool(groups), "empty training observations")
    vector = np.zeros(book.dimension, dtype=np.complex128)
    if enabled:
        for key in sorted(groups):
            parts, counts = groups[key]
            total = sum(counts.values())
            target = sum((book.code("value", label) * (n / total) for label, n in sorted(counts.items())))
            vector += np.conj(book.key(parts)) * target
    stats = {"observations": sum(sum(x[1].values()) for x in groups.values()),
             "contexts": len(groups), "conflicting_contexts": sum(len(x[1]) > 1 for x in groups.values())}
    return Memory(book, vector, candidates), stats
````

## `plm_l1_v03/bridge.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/bridge.py`  
SHA256: `bf202a714a7ffc5b3112730ac6bfff90f315f4eea76120fa750c8972d9c8913f`

````python
"""Fixed v0.2 reader integration. Imported only by callers that request it."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "PLM-L1-v0.2"


def fixed_reader():
    if str(VENDOR) not in sys.path:
        sys.path.insert(1, str(VENDOR))
    from plm_l1_v02.runtime import PairReader
    return PairReader.load(VENDOR / "results" / "reader")


def translate(reader, packet, writer):
    recovered = reader.recover(packet)
    if recovered["status"] != "recovered":
        return {"status": "abstain", "reason": recovered["reason"], "packet": None}
    try:
        return {"status": "bridged", "packet": writer.encode(recovered["slots"]), "eligible_for_inference": False}
    except ValueError as error:
        return {"status": "abstain", "reason": str(error), "packet": None}
````

## `plm_l1_v03/features.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/features.py`  
SHA256: `eca5d53924f13268037282e1321038e15b7ec0eca24448aea90eb1c65701b0fe`

````python
"""Explicit lexical priors and automatically aligned prefix features.

No language-specific grammar, supplied emission labels or state traces.
The alignment/copy architecture IS a designed inductive bias, not discovered.
"""
import numpy as np
from .algebra import canonical, require

CONTENT = ("subject", "object", "predicate")
ROLES = CONTENT + ("polarity", "modality")
GOALS = ("subject", "object")
END = canonical(["end"])


def validate_meaning(meaning, candidates):
    require(type(meaning) is dict and set(meaning) == set(ROLES), "invalid_meaning_fields")
    require(all(type(meaning[r]) is str and meaning[r] in candidates[r] for r in ROLES), "unknown_meaning_value")


def validate_lexicon(lexicon):
    require(type(lexicon) is dict and set(lexicon) == {"tokens", "slot_candidates"}, "invalid_lexicon_fields")
    candidates = lexicon["slot_candidates"]
    require(type(candidates) is dict and set(candidates) == set(ROLES), "invalid_slot_inventory")
    for values in candidates.values():
        require(type(values) is list and len(values) >= 2 and all(type(v) is str and v for v in values) and len(set(values)) == len(values), "invalid_candidates")
    require(type(lexicon["tokens"]) is list and 0 < len(lexicon["tokens"]) <= 256, "invalid_tokens")
    surfaces, meanings = set(), set()
    for token in lexicon["tokens"]:
        require(type(token) is dict and set(token) == {"surface", "kind", "value"}, "invalid_lexical_fields")
        surface, kind, value = token["surface"], token["kind"], token["value"]
        require(type(surface) is str and 0 < len(surface) <= 32 and surface not in surfaces, "invalid_surface")
        require(kind in ("entity", "predicate", "marker"), "invalid_kind")
        if kind == "marker":
            require(value is None, "marker_semantics_prohibited")
        else:
            require(type(value) is str and value.startswith(kind + ":") and value not in meanings, "ambiguous_lexical_realization")
            require(any(value in candidates[r] for r in CONTENT), "lexical_value_outside_candidates")
            meanings.add(value)
        surfaces.add(surface)


def tokenize(text, vocabulary):
    require(type(text) is str and 0 < len(text) <= 256, "empty_or_oversized_text")
    ordered = sorted(vocabulary, key=lambda s: (-len(s), s))
    offset, tokens = 0, []
    while offset < len(text):
        token = next((t for t in ordered if text.startswith(t, offset)), None)
        require(token is not None, "unknown_token")
        tokens.append(token)
        require(len(tokens) <= 9, "token_capacity_exceeded")
        offset += len(token)
    return tokens


def aligned_examples(pairs, lexicon):
    """Infer abstract emissions from lexical identity and paired semantic slots.

    Prefixes and next-symbol targets are derived internally from these pairs.
    This is supervised sequence learning, not elimination of all supervision.
    """
    validate_lexicon(lexicon)
    require(type(pairs) is list and 0 < len(pairs) <= 10000, "invalid_pair_collection")
    vocabulary = {t["surface"]: t for t in lexicon["tokens"]}
    seen = {}
    output = []
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"text", "meaning"}, "only_text_and_meaning_allowed")
        meaning = pair["meaning"]
        validate_meaning(meaning, lexicon["slot_candidates"])
        tokens = tokenize(pair["text"], vocabulary)
        require(pair["text"] not in seen or seen[pair["text"]] == canonical(meaning), "contradictory_duplicate_text")
        seen[pair["text"]] = canonical(meaning)
        sequence, used, first = [], set(), None
        for surface in tokens:
            token = vocabulary[surface]
            if token["kind"] == "marker":
                sequence.append(canonical(["literal", surface]))
            else:
                roles = [r for r in CONTENT if meaning[r] == token["value"]]
                require(len(roles) == 1 and roles[0] not in used, "ambiguous_or_repeated_alignment")
                role = roles[0]
                used.add(role)
                first = first or role
                sequence.append(canonical(["slot", role]))
        require(used == set(CONTENT) and first in GOALS, "incomplete_or_unsupported_alignment")
        output.append({"meaning": dict(meaning), "goal": first, "sequence": sequence})
    return output


class Space:
    def __init__(self, book, use_prefix=True, use_status=True):
        self.book, self.use_prefix, self.use_status = book, use_prefix, use_status
        self.cache = {}

    def context(self, meaning, goal, prefix=None):
        result = {"goal": goal}
        if self.use_status:
            result.update({r: meaning[r] for r in ("polarity", "modality")})
        if prefix is not None:
            result["prefix"] = list(prefix) if self.use_prefix else []
        return result

    def key(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            value = np.ones(self.book.dimension, dtype=np.complex128)
            for field in sorted(description):
                if field == "prefix":
                    value *= self.book.code("prefix_boundary", "present")
                    for i, symbol in enumerate(description[field]):
                        value *= np.roll(self.book.code("emitted_symbol", symbol), 17 * i)
                else:
                    value *= self.book.code("context_" + field, description[field])
            self.cache[identity] = value
        return self.cache[identity]
````

## `plm_l1_v03/memory.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/memory.py`  
SHA256: `c773d85c99219b286cb08b7835b6c046133af9365b966d0c08663023104a0b33`

````python
"""Balanced phase association; no context table retained after fitting."""
import numpy as np
from .algebra import canonical, require


class Association:
    def __init__(self, space, vector, candidates):
        self.space = space
        self.vector = np.asarray(vector, dtype=np.complex128).copy()
        require(self.vector.shape == (space.book.dimension,) and np.isfinite(self.vector).all(), "invalid_weights")
        self.candidates = tuple(sorted(set(candidates)))
        require(bool(self.candidates), "empty_candidates")
        self.basis = np.array([space.book.code("value", c).conj() for c in self.candidates])
        self.cache = {}

    def recall(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            scores = np.real(self.basis @ (self.vector * self.space.key(description))) / self.space.book.dimension
            order = np.argsort(-scores, kind="stable")
            top = float(scores[order[0]])
            runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
            self.cache[identity] = {"value": self.candidates[order[0]] if top >= .65 and top - runner >= .25 else None,
                                    "score": round(top, 8), "margin": round(top - runner, 8)}
        return dict(self.cache[identity])


def fit_memory(space, observations, enabled=True):
    groups, candidates = {}, set()
    for key, target in observations:
        identity = canonical(key)
        if identity not in groups:
            groups[identity] = [key, {}]
        counts = groups[identity][1]
        counts[target] = counts.get(target, 0) + 1
        candidates.add(target)
    require(0 < len(groups) <= 256, "association_capacity_exceeded")
    vector = np.zeros(space.book.dimension, dtype=np.complex128)
    if enabled:
        for identity in sorted(groups):
            key, counts = groups[identity]
            mean = sum(space.book.code("value", value) * (n / sum(counts.values())) for value, n in sorted(counts.items()))
            vector += space.key(key).conj() * mean
    return Association(space, vector, candidates), {"contexts": len(groups), "observations": len(observations),
             "conflicting_contexts": sum(len(row[1]) > 1 for row in groups.values())}
````

## `plm_l1_v03/runtime.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/runtime.py`  
SHA256: `0aaf777f08e84ffddf8829aa1f154c42aaf02f89d4ff40a252bd1c8ce6fdfeb1`

````python
"""Autoregressive phase writer. No reader, teacher, corpus or old model imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require
from .features import ROLES, CONTENT, GOALS, Space, END, validate_meaning
from .memory import Association

MEMORIES = ("support", "steps", "lexical")


def abstain(reason, **extra):
    return dict(status="abstain", reason=reason, text=None, eligible_for_inference=False, **extra)


class Writer:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-pair-writer-v1" and self.meta.get("eligible_for_inference") is False, "invalid_metadata")
        require(set(memories) == set(MEMORIES), "invalid_memory_inventory")
        require(set(self.meta["slot_candidates"]) == set(ROLES), "invalid_slot_inventory")
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.space = Space(self.book, self.meta["use_prefix"], self.meta["use_status"])
        self.memories = memories
        for memory in memories.values():
            require(memory.vector.shape == (self.book.dimension,), "weight_dimension_mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {
            name: {"sha256": hashlib.sha256(memory.vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(memory.candidates)}
            for name, memory in sorted(memories.items())}})
        self.slot_basis = {r: np.array([self.book.code("value", v).conj() for v in self.meta["slot_candidates"][r]]) for r in ROLES}

    def encode(self, meaning):
        """Explicit meaning-to-signal boundary; not a text parser or generator."""
        validate_meaning(meaning, self.meta["slot_candidates"])
        vector = sum(self.book.code("semantic_role", r) * self.book.code("value", meaning[r]) for r in ROLES)
        return {"schema": "plm-l1-writer-meaning-v1", "writer_fingerprint": self.fingerprint,
                "dimension": self.book.dimension, "real": vector.real.tolist(), "imag": vector.imag.tolist(), "eligible_for_inference": False}

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {"schema", "writer_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
            require(packet["schema"] == "plm-l1-writer-meaning-v1" and packet["writer_fingerprint"] == self.fingerprint, "packet_writer_mismatch")
            require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension and packet["eligible_for_inference"] is False, "invalid_packet_contract")
            for field in ("real", "imag"):
                require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(x) in (int, float) for x in packet[field]), "invalid_signal_values")
            vector = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32., "invalid_signal")
            clean = np.zeros(self.book.dimension, dtype=np.complex128)
            meaning, audit = {}, {}
            for role in ROLES:
                scores = np.real(self.slot_basis[role] @ (vector * self.book.code("semantic_role", role).conj())) / self.book.dimension
                order = np.argsort(-scores, kind="stable")
                top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
                require(top >= .65 and top - runner >= .25, "ambiguous_meaning")
                meaning[role] = self.meta["slot_candidates"][role][order[0]]
                audit[role] = {"score": round(top, 8), "margin": round(top - runner, 8)}
                clean += self.book.code("semantic_role", role) * self.book.code("value", meaning[role])
            residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
            require(residual <= .20, "meaning_residual_excessive")
            return {"status": "recovered", "meaning": meaning, "audit": audit, "residual": round(residual, 8)}
        except (ValueError, TypeError, OverflowError) as error:
            return {"status": "abstain", "reason": str(error), "meaning": None}

    def generate(self, packet, goal="object", *, max_steps=12):
        if type(goal) is not str or goal not in GOALS:
            return abstain("unsupported_goal")
        if type(max_steps) is not int or not 1 <= max_steps <= 64:
            return abstain("invalid_step_budget")
        decoded = self.recover(packet)
        if decoded["status"] != "recovered":
            return abstain(decoded["reason"])
        meaning = decoded["meaning"]
        support = self.memories["support"].recall(self.space.context(meaning, goal))
        if support["value"] != "supported":
            return abstain("unsupported_meaning_goal")
        prefix, text, used, trace = [], [], set(), []
        for step in range(max_steps):
            selected = self.memories["steps"].recall(self.space.context(meaning, goal, prefix))
            symbol = selected["value"]
            trace.append({"step": step, **selected})
            if symbol is None:
                return abstain("next_symbol_unresolved", trace=trace)
            if symbol == END:
                if used != set(CONTENT):
                    return abstain("premature_end", trace=trace)
                return {"status": "generated", "text": "".join(text), "trace": trace, "eligible_for_inference": False}
            kind, value = json.loads(symbol)
            if kind == "slot":
                if value not in CONTENT or value in used or (not used and value != goal):
                    return abstain("invalid_role_emission", trace=trace)
                surface = self.memories["lexical"].recall({"lexical_value": meaning[value]})["value"]
                if surface is None or self.meta["surfaces"].get(surface) not in ("entity", "predicate"):
                    return abstain("lexical_realization_unresolved", trace=trace)
                used.add(value)
            elif kind == "literal" and self.meta["surfaces"].get(value) == "marker":
                surface = value
            else:
                return abstain("invalid_emission", trace=trace)
            prefix.append(symbol)
            text.append(surface)
            if len(prefix) > 9 or len("".join(text)) > 256:
                return abstain("output_capacity_exceeded", trace=trace)
        return abstain("step_budget_exhausted", trace=trace)

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "writer.json").exists() and not (target / "weights.npz").exists(), "writer_output_exists")
        info = {"metadata": self.meta, "fingerprint": self.fingerprint, "candidates": {k: list(v.candidates) for k, v in self.memories.items()}}
        with (target / "writer.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        np.savez_compressed(target / "weights.npz", **{k: v.vector for k, v in self.memories.items()})

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "writer.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "candidates"} and set(info["candidates"]) == set(MEMORIES), "invalid_writer_envelope")
        meta = info["metadata"]
        space = Space(Book(meta["dimension"], meta["seed"]), meta["use_prefix"], meta["use_status"])
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            require(set(weights.files) == set(MEMORIES), "invalid_weight_names")
            memories = {k: Association(space, weights[k], info["candidates"][k]) for k in MEMORIES}
        writer = cls(meta, memories)
        require(writer.fingerprint == info["fingerprint"], "writer_hash_mismatch")
        return writer
````

## `plm_l1_v03/training.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/plm_l1_v03/training.py`  
SHA256: `f73eae184f09e356e2adf41325c575a813543dc0d1b5ab29490504e0d2f66af6`

````python
"""Training API takes pairs/lexical prior, never old readers or writer traces."""
from .algebra import Book, canonical, digest, require
from .features import aligned_examples, Space, END
from .memory import fit_memory
from .runtime import Writer


def fit(pairs, lexicon, *, seed="writer-development-0", dimension=8192,
        pair_learning=True, use_prefix=True, use_status=True):
    require(all(type(v) is bool for v in (pair_learning, use_prefix, use_status)), "invalid_switches")
    examples = aligned_examples(pairs, lexicon)
    space = Space(Book(dimension, seed), use_prefix, use_status)
    rows = {"support": [], "steps": [], "lexical": []}
    for example in examples:
        meaning, goal, sequence = example["meaning"], example["goal"], example["sequence"]
        rows["support"].append((space.context(meaning, goal), "supported"))
        for i, symbol in enumerate(sequence + [END]):
            rows["steps"].append((space.context(meaning, goal, sequence[:i]), symbol))
    for token in lexicon["tokens"]:
        if token["kind"] != "marker":
            rows["lexical"].append(({"lexical_value": token["value"]}, token["surface"]))
    memories, stats = {}, {}
    for name, observations in rows.items():
        memories[name], stats[name] = fit_memory(space, observations, name == "lexical" or pair_learning)
    metadata = {"schema": "plm-l1-pair-writer-v1", "dimension": dimension, "seed": seed,
                "use_prefix": use_prefix, "use_status": use_status, "pair_learning": pair_learning,
                "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)),
                "lexicon_digest": digest(lexicon), "slot_candidates": lexicon["slot_candidates"],
                "surfaces": {t["surface"]: t["kind"] for t in lexicon["tokens"]},
                "statistics": stats, "supervision_fields": ["text", "meaning"],
                "supplied_trace_supervision": False, "automatic_alignment": True,
                "eligible_for_inference": False}
    return Writer(metadata, memories)
````

## `release_tools.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/release_tools.py`  
SHA256: `4799c39fd6e7665c2927e5dc9111be83ae5ad5765101eb97f924b8caefd01ab7`

````python
"""Additive source freezing, preservation checks, demo and ZIP release."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from evaluate import ROOT, source_files
from plm_l1_v03.algebra import digest
from plm_l1_v03.runtime import Writer
from plm_l1_v03.bridge import fixed_reader, translate, VENDOR


def hashes(files, root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "check-baseline", "demo", "pack"))
    command = parser.parse_args().command
    if command == "freeze":
        manifest = {"schema": "plm-l1-v03-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif command == "check-baseline":
        files = []
        for name in ("PLM-L1-v0.1", "PLM-L1-v0.2", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        baseline = json.loads((ROOT / "verification" / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        if hashes(files, ROOT.parent) != baseline:
            raise ValueError("old release changed")
        source = ROOT.parent / "PLM-L1-v0.2"
        if hashes([p for p in source.rglob("*") if p.is_file()], source) != hashes([p for p in VENDOR.rglob("*") if p.is_file()], VENDOR):
            raise ValueError("vendored v0.2 changed")
        print(json.dumps({"status": "unchanged", "preserved_files": len(files), "vendor_files": len(list(p for p in VENDOR.rglob("*") if p.is_file()))}))
    elif command == "demo":
        writer = Writer.load(ROOT / "results" / "writer")
        reader = fixed_reader()
        rows = []
        for text in ("太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。", "太郎は花子を助けた。"):
            read = reader.read(text)
            row = {"input": text, "read_status": read["status"], "reason": read["reason"]}
            if read["status"] == "read":
                packet = translate(reader, read["packet"], writer)["packet"]
                row["meaning"] = writer.recover(packet)["meaning"]
                row["generated"] = {goal: writer.generate(packet, goal) for goal in ("subject", "object")}
                if not rows:
                    write(ROOT / "examples" / "MEANING.json", row["meaning"])
                    write(ROOT / "examples" / "WRITER_MEANING_PACKET.json", packet)
            rows.append(row)
        write(ROOT / "examples" / "ROUNDTRIPS.json", {"scope": "Human/evaluator only, not input to generator", "demos": rows})
    else:
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts)
        write(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v03-release-v1", "files": hashes(files, ROOT)})
        archive = ROOT.parent / "PLM-L1-v0.3.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with (ROOT.parent / "PLM-L1-v0.3.sha256").open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(files) + 1, "sha256": checksum}))


if __name__ == "__main__":
    main()
````

## `requirements.txt`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/requirements.txt`  
SHA256: `7bd6b8946940b79948c548c8048e545684b91c8edc9444d8dfc0c8f76a97c0a7`

````text
numpy==2.3.5
````

## `tests/test_writer.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/tests/test_writer.py`  
SHA256: `4369d54b2cec41173026b2b70ae7c0bd6a35f73e6c121f99f26db0840d3eee7d`

````python
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v03.algebra import Book, canonical
from plm_l1_v03.features import aligned_examples, Space, GOALS, END
from plm_l1_v03.training import fit
from plm_l1_v03.runtime import Writer
from plm_l1_v03.memory import Association
from plm_l1_v03.bridge import fixed_reader, translate
from evaluation_support import data, oracle, transform, score, LookupWriter
from evaluate import bad_packets


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, cls.dev, cls.lex = data("train"), data("development"), data("lexicon")
        cls.writer = fit(cls.train, cls.lex)
        cls.reader = fixed_reader()
        interpret, invalid, patterns = oracle()
        cls.interpret, cls.invalid, cls.patterns = staticmethod(interpret), invalid, patterns
        cls.text = "太郎が花子を助けた。"
        cls.meaning = interpret(cls.text)
        cls.packet = cls.writer.encode(cls.meaning)

    def test_standalone_all_development(self):
        for row in self.dev:
            packet = self.writer.encode(row["meaning"])
            for goal in GOALS:
                out = self.writer.generate(packet, goal)
                s = score(out["text"], row["meaning"], goal, "full", self.interpret, self.patterns)
                self.assertEqual(out["status"], "generated")
                self.assertTrue(s["meaning_exact"] and s["goal_exact"])

    def test_fixed_reader_roundtrips_all_development(self):
        for row in self.dev:
            reading = self.reader.read(row["text"])
            packet = translate(self.reader, reading["packet"], self.writer)["packet"]
            for goal in GOALS:
                out = self.writer.generate(packet, goal)
                self.assertEqual(self.interpret(out["text"]), row["meaning"])

    def test_no_legacy_teacher_reader_or_generator_used(self):
        import plm_l1.teacher as teacher
        from plm_l1.runtime import Model
        with patch.object(teacher, "reader_trace", side_effect=AssertionError("forbidden")), patch.object(teacher, "writer_trace", side_effect=AssertionError("forbidden")), patch.object(Model, "generate", side_effect=AssertionError("forbidden")), patch.object(Model, "read", side_effect=AssertionError("forbidden")), patch.object(type(self.reader), "read", side_effect=AssertionError("forbidden")):
            model = fit(self.train, self.lex)
            self.assertEqual(model.generate(model.encode(self.meaning))["text"], "花子を太郎が助けた。")

    def test_fit_api_fields(self):
        self.assertEqual(list(inspect.signature(fit).parameters), ["pairs", "lexicon", "seed", "dimension", "pair_learning", "use_prefix", "use_status"])
        for field in ("actions", "states", "trace", "reader_trace", "writer_trace", "order", "goal", "id", "token_roles"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                fit([dict(self.train[0], **{field: []})], self.lex)

    def test_automatic_alignment_and_stop(self):
        examples = aligned_examples(self.train, self.lex)
        self.assertEqual(len(examples), 576)
        self.assertEqual({r["goal"] for r in examples}, set(GOALS))
        self.assertTrue(all(len(r["sequence"]) in (7, 8) for r in examples))
        self.assertIn(END, self.writer.memories["steps"].candidates)
        self.assertFalse(self.writer.meta["supplied_trace_supervision"])
        self.assertEqual(self.writer.meta["statistics"]["steps"]["contexts"], 68)

    def test_no_marker_meanings(self):
        self.assertTrue(all(t["value"] is None for t in self.lex["tokens"] if t["kind"] == "marker"))
        lex = copy.deepcopy(self.lex)
        next(t for t in lex["tokens"] if t["kind"] == "marker")["value"] = "polarity:negative"
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_conflicting_duplicate_text(self):
        other = copy.deepcopy(self.train[0])
        other["meaning"]["polarity"] = "polarity:negative" if other["meaning"]["polarity"] == "polarity:positive" else "polarity:positive"
        with self.assertRaises(ValueError):
            fit([self.train[0], other], self.lex)

    def test_ambiguous_alignment(self):
        row = {"text": "太郎が太郎を助けた。", "meaning": self.interpret("太郎が太郎を助けた。")}
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_missing_alignment(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["predicate"] = "predicate:gaze_at" if row["meaning"]["predicate"] != "predicate:gaze_at" else "predicate:help"
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_unknown_training_word(self):
        with self.assertRaises(ValueError):
            fit([{"text": "未知が花子を助けた。", "meaning": self.meaning}], self.lex)

    def test_extra_meaning_field(self):
        with self.assertRaises(ValueError):
            self.writer.encode(dict(self.meaning, state="S0"))

    def test_unknown_meaning(self):
        with self.assertRaises(ValueError):
            self.writer.encode(dict(self.meaning, subject="entity:未知"))

    def test_duplicate_surface(self):
        lex = copy.deepcopy(self.lex)
        lex["tokens"].append(copy.deepcopy(lex["tokens"][0]))
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_ambiguous_lexical_realization(self):
        lex = copy.deepcopy(self.lex)
        token = copy.deepcopy(next(t for t in lex["tokens"] if t["kind"] == "entity"))
        token["surface"] = "別名"
        lex["tokens"].append(token)
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_balanced_duplicates(self):
        model = fit(self.train + self.train, self.lex)
        for name in self.writer.memories:
            np.testing.assert_array_equal(model.memories[name].vector, self.writer.memories[name].vector)

    def test_order_determinism(self):
        self.assertEqual(fit(list(reversed(self.train)), self.lex).fingerprint, self.writer.fingerprint)

    def test_no_full_sentences_or_context_tables_saved(self):
        serial = canonical(self.writer.meta)
        self.assertTrue(all(r["text"] not in serial for r in self.train))
        for memory in self.writer.memories.values():
            self.assertFalse(hasattr(memory, "groups"))
            self.assertTrue(all(r["text"] not in canonical(memory.candidates) for r in self.train))

    def test_no_pair_learning_keeps_lexicon(self):
        model = fit(self.train, self.lex, pair_learning=False)
        self.assertEqual(model.memories["lexical"].recall({"lexical_value": "entity:太郎"})["value"], "太郎")
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "abstain")

    def test_no_prefix_is_ambiguous(self):
        model = fit(self.train, self.lex, use_prefix=False)
        self.assertGreater(model.meta["statistics"]["steps"]["conflicting_contexts"], 0)
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "abstain")

    def test_no_status_is_ambiguous(self):
        model = fit(self.train, self.lex, use_status=False)
        self.assertGreater(model.meta["statistics"]["steps"]["conflicting_contexts"], 0)
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "abstain")

    def test_roles_follow_teacher_change(self):
        rows, lex = transform(self.train, self.lex, "roles_swapped")
        model = fit(rows, lex)
        out = model.generate(model.encode(self.meaning))
        self.assertEqual(out["text"], "花子が太郎を助けた。")
        self.assertTrue(score(out["text"], self.meaning, "object", "roles_swapped", self.interpret, self.patterns)["meaning_exact"])

    def test_states_follow_teacher_change(self):
        rows, lex = transform(self.train, self.lex, "states_flipped")
        model = fit(rows, lex)
        self.assertEqual(model.generate(model.encode(self.meaning))["text"], "もし花子を太郎が助けなかったら。")

    def test_opaque_markers(self):
        rows, lex = transform(self.train, self.lex, "markers_renamed")
        model = fit(rows, lex)
        out = model.generate(model.encode(self.meaning))
        self.assertIn("~M", out["text"])
        self.assertTrue(score(out["text"], self.meaning, "object", "markers_renamed", self.interpret, self.patterns)["meaning_exact"])

    def test_withheld_negative_abstains(self):
        model = fit([r for r in self.train if r["meaning"]["polarity"] == "polarity:positive"], self.lex)
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "generated")
        self.assertEqual(model.generate(model.encode(dict(self.meaning, polarity="polarity:negative")))["status"], "abstain")

    def test_withheld_style_not_preinstalled(self):
        pairs = [r for r, e in zip(self.train, aligned_examples(self.train, self.lex)) if e["goal"] == "subject"]
        model = fit(pairs, self.lex)
        self.assertEqual(model.generate(model.encode(self.meaning), "object")["status"], "abstain")
        self.assertEqual(model.generate(model.encode(self.meaning), "subject")["text"], self.text)

    def test_prefix_order_is_not_commutative(self):
        space = Space(Book())
        a = space.context(self.meaning, "subject", ["a", "b"])
        b = space.context(self.meaning, "subject", ["b", "a"])
        self.assertGreater(np.linalg.norm(space.key(a) - space.key(b)), 1.)

    def test_prefix_abstracts_content_values(self):
        space = Space(Book())
        a = space.context(self.meaning, "subject", [canonical(["slot", "subject"])])
        other = dict(self.meaning, subject="entity:次郎")
        self.assertEqual(a, space.context(other, "subject", a["prefix"]))

    def test_role_bound_signals_differ(self):
        other = self.writer.encode(dict(self.meaning, subject=self.meaning["object"], object=self.meaning["subject"]))
        self.assertNotEqual(other["real"], self.packet["real"])

    def test_packet_contains_only_signal(self):
        self.assertEqual(set(self.packet), {"schema", "writer_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        self.assertNotIn("太郎", canonical(self.packet))

    def test_invalid_packets(self):
        for i, packet in enumerate(bad_packets(self.writer, self.meaning)):
            with self.subTest(case=i):
                self.assertEqual(self.writer.generate(packet)["status"], "abstain")

    def test_more_packet_extra_fields(self):
        for field in ("gold", "trace", "actions", "source", "goal", "metadata"):
            self.assertEqual(self.writer.generate(dict(self.packet, **{field: []}))["status"], "abstain")

    def test_packet_nonobjects(self):
        for value in (None, [], "text", 1, True):
            self.assertEqual(self.writer.generate(value)["status"], "abstain")

    def test_mismatched_signal_lengths(self):
        self.assertEqual(self.writer.generate(dict(self.packet, real=self.packet["real"][:-1]))["status"], "abstain")

    def test_unknown_goal(self):
        for goal in ("essay", None, [], True):
            self.assertEqual(self.writer.generate(self.packet, goal)["status"], "abstain")

    def test_step_budget(self):
        self.assertEqual(self.writer.generate(self.packet, max_steps=1)["reason"], "step_budget_exhausted")
        self.assertIsNone(self.writer.generate(self.packet, max_steps=1)["text"])
        for budget in (0, 65, True):
            self.assertEqual(self.writer.generate(self.packet, max_steps=budget)["status"], "abstain")

    def test_premature_stop_guard(self):
        with patch.object(self.writer.memories["steps"], "recall", return_value={"value": END}):
            self.assertEqual(self.writer.generate(self.packet)["reason"], "premature_end")

    def test_repeated_role_guard(self):
        with patch.object(self.writer.memories["steps"], "recall", return_value={"value": canonical(["slot", "object"])}):
            self.assertEqual(self.writer.generate(self.packet)["reason"], "invalid_role_emission")

    def test_missing_stop_bounded(self):
        with patch.object(self.writer.memories["steps"], "recall", return_value={"value": canonical(["literal", "。"]) }):
            self.assertEqual(self.writer.generate(self.packet)["reason"], "output_capacity_exceeded")

    def test_lexical_memory_required(self):
        memories = dict(self.writer.memories)
        old = memories["lexical"]
        memories["lexical"] = Association(old.space, np.zeros(old.space.book.dimension), old.candidates)
        model = Writer(self.writer.meta, memories)
        self.assertEqual(model.generate(model.encode(self.meaning))["reason"], "lexical_realization_unresolved")

    def test_self_reference_generation(self):
        meaning = dict(self.meaning, object=self.meaning["subject"])
        self.assertEqual(self.writer.generate(self.writer.encode(meaning))["text"], "太郎を太郎が助けた。")

    def test_negative_hypothetical(self):
        meaning = dict(self.meaning, polarity="polarity:negative", modality="modality:hypothetical")
        self.assertEqual(self.writer.generate(self.writer.encode(meaning))["text"], "もし花子を太郎が助けなかったら。")

    def test_reading_signal_bridge(self):
        reading = self.reader.read(self.text)
        bridged = translate(self.reader, reading["packet"], self.writer)
        self.assertEqual(self.writer.recover(bridged["packet"])["meaning"], self.meaning)
        self.assertEqual(translate(self.reader, {}, self.writer)["status"], "abstain")

    def test_fixed_reader_unchanged(self):
        self.assertEqual(self.reader.fingerprint, fixed_reader().fingerprint)
        self.assertEqual(self.reader.fingerprint, "fd7635ee535b265995c3e95d22f01493b2216472fe9e1e7976104a666a32bec1")

    def test_invalid_read_inputs(self):
        for text in self.invalid:
            self.assertEqual(self.reader.read(text)["status"], "abstain")

    def test_inference_remains_disabled(self):
        self.assertFalse(self.packet["eligible_for_inference"])
        self.assertFalse(self.writer.generate(self.packet)["eligible_for_inference"])

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            model = Writer.load(temp)
            self.assertEqual(model.fingerprint, self.writer.fingerprint)
            self.assertEqual(model.generate(self.packet), self.writer.generate(self.packet))

    def test_save_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            with self.assertRaises(ValueError):
                self.writer.save(temp)

    def test_metadata_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            path = Path(temp) / "writer.json"
            info = json.loads(path.read_text(encoding="utf-8"))
            info["metadata"]["pair_count"] += 1
            path.write_text(json.dumps(info), encoding="utf-8")
            with self.assertRaises(ValueError):
                Writer.load(temp)

    def test_weights_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            path = Path(temp) / "weights.npz"
            with np.load(path, allow_pickle=False) as weights:
                arrays = {k: weights[k] for k in weights.files}
            arrays["steps"][0] += 1
            np.savez_compressed(path, **arrays)
            with self.assertRaises(ValueError):
                Writer.load(temp)

    def test_invalid_fit_configuration(self):
        for kwargs in ({"dimension": 129}, {"use_prefix": 1}, {"seed": ""}):
            with self.assertRaises(ValueError):
                fit(self.train, self.lex, **kwargs)
        with self.assertRaises(ValueError):
            fit([], self.lex)

    def test_composition_split_disjoint(self):
        keys = lambda rows: {(r["meaning"]["subject"], r["meaning"]["object"], r["meaning"]["predicate"]) for r in rows}
        a, b, c = keys(self.train), keys(self.dev), keys(data("evaluation"))
        self.assertFalse(a & b or a & c or b & c)

    def test_ordinary_reference(self):
        model = LookupWriter(self.train, self.lex)
        for row in self.dev:
            for goal in GOALS:
                out = model.generate(row["meaning"], goal)
                self.assertEqual(self.interpret(out), row["meaning"])

    def test_core_has_no_language_or_legacy_imports(self):
        from plm_l1_v03 import training, runtime, features, memory
        for module in (training, runtime, features, memory):
            code = inspect.getsource(module)
            for text in ("from plm_l1.", "from plm_l1_v02", "import teacher", "from evaluation_support", "太郎", "花子", "もし", "なかった", '"が"', '"を"'):
                self.assertNotIn(text, code)


if __name__ == "__main__":
    unittest.main()
````

## `verify_release.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/verify_release.py`  
SHA256: `7795f4338c4a1c9fdc358726a50b9e6f537a1d28ab72a0ac3ab42539a40799fa`

````python
"""Tests and physical separation of pair learning, reading and generation."""
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
from evaluation_support import ROOT, data, oracle
from plm_l1_v03.algebra import digest
from plm_l1_v03.runtime import Writer
from plm_l1_v03.bridge import fixed_reader, translate, VENDOR


def run(arguments, cwd, output, label, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    completed = subprocess.run([sys.executable, "-B", *arguments], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    log = completed.stdout + completed.stderr
    (output / (label + ".log")).write_text(log, encoding="utf-8")
    if completed.returncode != expected:
        raise ValueError(label + " failed: " + log[-2000:])
    return completed.stdout, log


def copy_package(source, target, names=None):
    target.mkdir(parents=True)
    for path in sorted(source.glob("*.py")):
        if names is None or path.name in names:
            shutil.copyfile(path, target / path.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("fresh verification directory required")
    output.mkdir(parents=True)
    if args.preflight:
        from plm_l1_v03.training import fit
        writer = fit(data("train"), data("lexicon"))
        freeze, claimed, checks = "preflight_not_frozen", None, []
    else:
        freeze = verify_freeze()
        result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
        claimed = result.pop("result_digest")
        if digest(result) != claimed or result["freeze_hash"] != freeze:
            raise ValueError("evaluation integrity failure")
        protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
        checks = judge(result["results"], protocol)
        if checks != result["checks"] or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        writer = Writer.load(ROOT / "results" / "writer")
    test_counts = {}
    for label, cwd in (("NEW_TESTS", ROOT), ("V02_TESTS", VENDOR), ("V01_TESTS", VENDOR / "vendor" / "PLM-L1-v0.1")):
        _, log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], cwd, output, label)
        test_counts[label] = int(re.search(r"Ran (\d+) tests", log).group(1))

    # New writer learns with no old package, reader, teacher or weights present.
    writer_only = output / "writer-training-only"
    copy_package(ROOT / "plm_l1_v03", writer_only / "plm_l1_v03")
    for name in ("train.json", "lexicon.json"):
        shutil.copyfile(ROOT / "data" / name, writer_only / name)
    assertion = "from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert importlib.util.find_spec('plm_l1') is None; assert importlib.util.find_spec('plm_l1_v02') is None; assert not Path('evaluation.json').exists(); print('writer: no reader, no old teacher, no old weights, no evaluation data')"
    run(["-c", assertion], writer_only, output, "WRITER_TRAIN_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v03", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", writer.meta["seed"], "--out", "model"], writer_only, output, "WRITER_PAIR_TRAIN")
    if json.loads(stdout)["writer_fingerprint"] != writer.fingerprint:
        raise ValueError("isolated writer differs")

    # Independently demonstrate that the unchanged v0.2 reader also learns only
    # from pairs/lexicon, with its old teacher and generator weights absent.
    reader_only = output / "reader-training-only"
    copy_package(VENDOR / "plm_l1_v02", reader_only / "plm_l1_v02")
    old_core = VENDOR / "vendor" / "PLM-L1-v0.1"
    minimal_old = reader_only / "vendor" / "PLM-L1-v0.1"
    copy_package(old_core / "plm_l1", minimal_old / "plm_l1", {"__init__.py", "__main__.py", "algebra.py", "runtime.py"})
    for name in ("train.json", "lexicon.json"):
        shutil.copyfile(ROOT / "data" / name, reader_only / name)
    assertion = "from pathlib import Path; from plm_l1_v02.compat import VENDOR; import importlib.util; assert not (VENDOR/'results').exists(); assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; assert not Path('evaluation.json').exists(); print('reader: no teacher, no old weights, no evaluation data')"
    run(["-c", assertion], reader_only, output, "READER_TRAIN_BOUNDARY")
    reader = fixed_reader()
    stdout, _ = run(["-m", "plm_l1_v02", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", reader.meta["seed"], "--out", "model"], reader_only, output, "READER_PAIR_TRAIN")
    if json.loads(stdout)["reader_fingerprint"] != reader.fingerprint:
        raise ValueError("isolated reader differs")

    # Generation-only surface contains no training code, corpora, reader or
    # legacy generation implementation. It receives only numerical packets.
    generation_only = output / "generation-only"
    copy_package(ROOT / "plm_l1_v03", generation_only / "plm_l1_v03", {"__init__.py", "__main__.py", "algebra.py", "features.py", "memory.py", "runtime.py"})
    shutil.copytree(writer_only / "model", generation_only / "model")
    assertion = "from pathlib import Path; import importlib.util; assert importlib.util.find_spec('plm_l1_v03.training') is None; assert importlib.util.find_spec('plm_l1_v03.bridge') is None; assert importlib.util.find_spec('plm_l1_v02') is None; assert importlib.util.find_spec('plm_l1') is None; assert not Path('train.json').exists(); print('generation: no reader, no old generator, no training code/data')"
    run(["-c", assertion], generation_only, output, "GENERATION_BOUNDARY")
    interpret, _, _ = oracle()
    texts = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。"]
    demos = []
    for i, text in enumerate(texts):
        source_packet = f"reader-{i}.json"
        run(["-m", "plm_l1_v02", "read", "--model", "model", "--text", text, "--out", source_packet], reader_only, output, f"READ_{i}")
        packet = json.loads((reader_only / source_packet).read_text(encoding="utf-8"))
        bridged = translate(reader, packet, writer)
        if bridged["status"] != "bridged":
            raise ValueError("isolation bridge failed")
        with (generation_only / f"meaning-{i}.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(bridged["packet"], ensure_ascii=False))
        stdout, _ = run(["-m", "plm_l1_v03", "generate", "--model", "model", "--packet", f"meaning-{i}.json", "--goal", "object"], generation_only, output, f"GENERATE_{i}")
        out = json.loads(stdout)
        if out["status"] != "generated" or interpret(out["text"]) != interpret(text):
            raise ValueError("isolated generation changed meaning")
        demos.append({"input": text, "output": out["text"], "meaning_exact": True})
    run(["-m", "plm_l1_v02", "read", "--model", "model", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], reader_only, output, "ABSTAIN", expected=2)
    if (reader_only / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")

    manifest_checked = False
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        manifest_checked = True
    report = {"status": "passed", "preflight": args.preflight, "source_freeze": freeze,
              "result_digest": claimed, "acceptance_checks": len(checks), "test_counts": test_counts,
              "writer_pair_fit_without_reader_teacher_legacy_weights": True,
              "reader_pair_fit_without_teacher_legacy_weights": True,
              "isolated_writer_and_reader_fingerprints_equal": True,
              "generation_without_reader_training_code_or_old_generator": True,
              "isolated_roundtrips": demos, "release_manifest_checked": manifest_checked,
              "full_numeric_rerun_in_this_command": False, "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

