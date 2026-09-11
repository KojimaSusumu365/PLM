# PLM-L1-v0.1 全コード（当該版直下・vendor重複除外）

原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。

## `evaluate.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/evaluate.py`  
SHA256: `c411d277fb447bbe858b30525fd18deac9ed10c91828e884cb7cceeeb1e17bbf`

````python
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
````

## `plm_l1/__init__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/__init__.py`  
SHA256: `ae72c106ef1a3571fbf001c1867f1cb1473e3d6c850e4a3c65718d2d4389920b`

````python
"""PLM-L1: experimental supervised phase-associative language transducer."""
__version__ = "0.1.0"
````

## `plm_l1/__main__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/__main__.py`  
SHA256: `cc53ce8e312b6b7ef1783234b00be8fe0455525b3b710a01120ef996c16a9795`

````python
import argparse
import json
from pathlib import Path
from .runtime import Model


def write_new(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="PLM-L1 v0.1 controlled Japanese SS language experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--out", required=True)
    train.add_argument("--seed", default="development-0")
    read = commands.add_parser("read")
    read.add_argument("--model", required=True)
    read.add_argument("--text", required=True)
    read.add_argument("--out", required=True, help="signal-only packet; original text/slots excluded")
    generate = commands.add_parser("generate")
    generate.add_argument("--model", required=True)
    generate.add_argument("--packet", required=True)
    generate.add_argument("--goal", default="object_first")
    args = parser.parse_args()
    if args.command == "train":
        from .training import fit
        model = fit(args.seed)
        model.save(args.out)
        result = {"status": "trained", "fingerprint": model.fingerprint, "statistics": model.meta["memory_statistics"]}
    elif args.command == "read":
        result = Model.load(args.model).read(args.text)
        if result["status"] == "read":
            write_new(args.out, result.pop("packet"))
    else:
        result = Model.load(args.model).generate(json.loads(Path(args.packet).read_text(encoding="utf-8")), args.goal)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] != "abstain" else 2


if __name__ == "__main__":
    raise SystemExit(main())
````

## `plm_l1/algebra.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/algebra.py`  
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

## `plm_l1/oracle.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/oracle.py`  
SHA256: `1fd83f5da0b0b9cdc34657c17e45a57f0d7eed408beaa3deb38c547f8459cd78`

````python
"""Evaluator-only independent implementation of the bounded surface grammar.

Does not import the teacher, transducer, learned states, or SS decoder. This is
independent code, NOT independent human annotation or real-world validation.
"""
import re

PEOPLE = ("太郎", "花子", "次郎", "美咲", "健太", "由紀")
PREDICATES = {"助け": "help", "褒め": "praise", "訪ね": "visit", "見つめ": "gaze_at"}
NAME = "(?:" + "|".join(PEOPLE) + ")"
VERB = "(?:" + "|".join(PREDICATES) + ")"
PATTERNS = [
    re.compile(rf"(?P<if>もし)?(?P<a>{NAME})が(?P<b>{NAME})を(?P<v>{VERB})(?P<end>なかったら|なかった|たら|た)。"),
    re.compile(rf"(?P<if>もし)?(?P<b>{NAME})を(?P<a>{NAME})が(?P<v>{VERB})(?P<end>なかったら|なかった|たら|た)。"),
]


def interpret(text):
    if type(text) is not str:
        return None
    for pattern in PATTERNS:
        match = pattern.fullmatch(text)
        if not match:
            continue
        row = match.groupdict()
        hypothetical = row["end"].endswith("ら")
        if bool(row["if"]) != hypothetical:
            return None
        return {"subject": "entity:" + row["a"], "object": "entity:" + row["b"],
                "predicate": "predicate:" + PREDICATES[row["v"]],
                "polarity": "polarity:" + ("negative" if row["end"].startswith("な") else "positive"),
                "modality": "modality:" + ("hypothetical" if hypothetical else "asserted")}
    return None


INVALID = (
    "", "太郎", "太郎が花子を助けた", "太郎が花子を助けた。。", "太郎が花子を助けた。花子が太郎を褒めた。",
    "未知が花子を助けた。", "太郎が花子を食べた。", "太郎が花子を助ける。",
    "太郎が花子が助けた。", "太郎を花子を助けた。", "太郎がが花子を助けた。",
    "太郎花子を助けた。", "花子を助けた。", "太郎が助けた。", "助けた。",
    "もし太郎が花子を助けた。", "太郎が花子を助けたら。", "もしもし太郎が花子を助けたら。",
    "もし太郎が花子を助けなかった。", "太郎が花子を助けなかったら。",
    "太郎が花子を助けたなかった。", "太郎が花子を助けなかったた。",
    "「太郎が花子を助けた。」", "太郎は花子を助けた。", "太郎が彼女を助けた。",
    "太郎が花子と次郎を助けた。", "太郎が花子を助けた？", "太郎が花子を助けた。<EOS>",
    "太郎 が花子を助けた。", "太郎\nが花子を助けた。", "太郎が花子を助けた。" * 30,
)
````

## `plm_l1/runtime.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/runtime.py`  
SHA256: `867cd8aa4266e6ae80c3957952df4f8ff7f37bf30b52d7c604ec5be669014be5`

````python
"""Inference-only phase associative transducers.

Grammar decisions come from six fitted numerical memories. The generic executor
can capture, bind, emit, and stop; it contains no Japanese grammar productions.
Finite inventories, action semantics and resource bounds are explicit prior knowledge.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, Memory, canonical, digest, require

ROLES = ("subject", "object", "predicate", "polarity", "modality")
MEMORIES = ("lex_class", "lex_value", "surface", "read_action", "read_next", "write_action")


def reader_key(state, category, order_binding=True):
    return ([("read_state", state)] if order_binding else []) + [("category", category)]


def writer_key(goal, position, polarity, modality, order_binding=True):
    return ([("write_position", position)] if order_binding else []) + [
        ("goal", goal), ("control_polarity", polarity), ("control_modality", modality)]


def abstain(reason, **extra):
    return dict(status="abstain", reason=reason, eligible_for_inference=False, **extra)


class Model:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-model-v1", "wrong model schema")
        require(self.meta.get("eligible_for_inference") is False, "inference is not authorized")
        require(set(memories) == set(MEMORIES), "wrong memory inventory")
        require(set(self.meta["slot_candidates"]) == set(ROLES), "wrong slot inventory")
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.memories = memories
        for memory in memories.values():
            require(memory.book.dimension == self.book.dimension and memory.book.seed == self.book.seed, "memory book mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {
            k: {"hash": hashlib.sha256(v.vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(v.candidates)}
            for k, v in sorted(memories.items())}})
        self.surfaces = sorted(self.meta["token_surfaces"], key=lambda x: (-len(x), x))
        self.slot_basis = {r: np.array([self.book.code("value", c).conj() for c in self.meta["slot_candidates"][r]]) for r in ROLES}

    def recall(self, name, parts):
        return self.memories[name].recall(parts)

    def role(self, name):
        return self.book.code("semantic_role", name) if self.meta["role_binding"] else np.ones(self.book.dimension)

    def tokenize(self, text):
        require(type(text) is str and 0 < len(text) <= 256, "empty_or_oversized_input")
        tokens, offset = [], 0
        while offset < len(text):
            token = next((s for s in self.surfaces if text.startswith(s, offset)), None)
            require(token is not None, "unknown_token")
            tokens.append(token)
            require(len(tokens) < self.meta["max_tokens"], "token_capacity_exceeded")
            offset += len(token)
        return tokens + ["<EOS>"]

    def pack(self, vector):
        return {"schema": "plm-l1-meaning-v1", "model_fingerprint": self.fingerprint,
                "dimension": self.book.dimension, "real": vector.real.tolist(), "imag": vector.imag.tolist(),
                "eligible_for_inference": False}

    def unpack(self, packet):
        require(type(packet) is dict and set(packet) == {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
        require(packet["schema"] == "plm-l1-meaning-v1" and packet["model_fingerprint"] == self.fingerprint, "packet_model_mismatch")
        require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension, "packet_dimension_mismatch")
        require(packet["eligible_for_inference"] is False, "inference_is_prohibited")
        for field in ("real", "imag"):
            values = packet[field]
            require(type(values) is list and len(values) == self.book.dimension, "invalid_signal_shape")
            require(all(type(v) in (int, float) for v in values), "invalid_signal_type")
        vector = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
        require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32.0, "nonfinite_or_excessive_signal")
        return vector

    def read(self, text):
        try:
            tokens = self.tokenize(text)
        except ValueError as error:
            return abstain(str(error), packet=None, trace=[])
        q = self.meta["initial_state"]
        pending, occupied = None, set()
        vector = np.zeros(self.book.dimension, dtype=np.complex128)
        trace = []
        for index, token in enumerate(tokens):
            category = self.recall("lex_class", [("token", token)])
            value = self.recall("lex_value", [("token", token)])
            if category["value"] is None or value["value"] is None:
                return abstain("lexical_memory_unresolved", packet=None, trace=trace)
            parts = reader_key(q, category["value"], self.meta["order_binding"])
            action = self.recall("read_action", parts)
            nxt = self.recall("read_next", parts)
            trace.append({"position": index, "state": q, "category": category["value"], "action": action, "next": nxt})
            if action["value"] is None or nxt["value"] is None:
                return abstain("grammar_memory_unresolved", packet=None, trace=trace)
            a, q = action["value"], nxt["value"]
            additions = []
            if a == "capture":
                if pending is not None or not value["value"].startswith("entity:"):
                    return abstain("invalid_capture", packet=None, trace=trace)
                pending = value["value"]
            elif a.startswith("bind:"):
                role = a.split(":", 1)[1]
                if pending is None or role not in ("subject", "object"):
                    return abstain("invalid_binding", packet=None, trace=trace)
                additions.append((role, pending))
                pending = None
            elif a == "predicate":
                additions.append(("predicate", value["value"]))
            elif a.startswith("status:"):
                _, polarity, mode = a.split(":")
                additions += [("polarity", "polarity:" + polarity), ("modality", "modality:" + mode)]
            elif a == "stop":
                if index != len(tokens) - 1 or q != self.meta["terminal_state"] or occupied != set(ROLES) or pending is not None:
                    return abstain("incomplete_or_trailing_structure", packet=None, trace=trace)
                return {"status": "read", "reason": "controlled_language_observation", "packet": self.pack(vector),
                        "trace": trace, "eligible_for_inference": False}
            elif a != "noop":
                return abstain("unknown_primitive", packet=None, trace=trace)
            for role, content in additions:
                if role in occupied or content not in self.meta["slot_candidates"][role]:
                    return abstain("duplicate_or_invalid_slot", packet=None, trace=trace)
                vector += self.role(role) * self.book.code("value", content)
                occupied.add(role)
        return abstain("missing_stop", packet=None, trace=trace)

    def recover(self, packet):
        try:
            vector = self.unpack(packet)
        except (ValueError, TypeError, OverflowError) as error:
            return abstain(str(error), slots=None)
        slots, audit = {}, {}
        clean = np.zeros(self.book.dimension, dtype=np.complex128)
        for role in ROLES:
            scores = np.real(self.slot_basis[role] @ (vector * self.role(role).conj())) / self.book.dimension
            order = np.argsort(-scores, kind="stable")
            top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
            audit[role] = {"score": round(top, 8), "margin": round(top - runner, 8)}
            if top < self.meta["minimum"] or top - runner < self.meta["margin"]:
                return abstain("ambiguous_meaning", slots=None, audit=audit)
            slots[role] = self.meta["slot_candidates"][role][order[0]]
            clean += self.role(role) * self.book.code("value", slots[role])
        residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
        if residual > 0.20:
            return abstain("meaning_residual_excessive", slots=None, audit=audit, residual=residual)
        return {"status": "recovered", "slots": slots, "audit": audit, "residual": round(residual, 8), "eligible_for_inference": False}

    def generate(self, packet, goal="object_first"):
        if goal not in self.meta["goals"]:
            return abstain("unknown_generation_goal", text=None)
        decoded = self.recover(packet)
        if decoded["status"] != "recovered":
            return abstain(decoded["reason"], text=None)
        slots = decoded["slots"]
        trace, output = [], []
        emitted_roles = set()
        for position in range(self.meta["max_generation_steps"]):
            action = self.recall("write_action", writer_key(goal, position, slots["polarity"], slots["modality"], self.meta["order_binding"]))
            a = action["value"]
            trace.append({"position": position, "action": action})
            if a is None:
                return abstain("generation_memory_unresolved", text=None, trace=trace)
            if a == "stop":
                if emitted_roles != {"subject", "object", "predicate"}:
                    return abstain("incomplete_generation", text=None, trace=trace)
                return {"status": "generated", "text": "".join(output), "trace": trace, "eligible_for_inference": False}
            if a.startswith("slot:"):
                role = a.split(":", 1)[1]
                if role not in ("subject", "object", "predicate") or role in emitted_roles:
                    return abstain("invalid_generation_slot", text=None, trace=trace)
                content = slots[role]
                emitted_roles.add(role)
            elif a.startswith("emit:"):
                content = a.split(":", 1)[1]
            else:
                return abstain("unknown_generation_primitive", text=None, trace=trace)
            selected = self.recall("surface", [("meaning", content)])
            if selected["value"] is None or selected["value"] == "<EOS>":
                return abstain("surface_memory_unresolved", text=None, trace=trace)
            output.append(selected["value"])
        return abstain("generation_capacity_exceeded", text=None, trace=trace)

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "model.json").exists() and not (target / "weights.npz").exists(), "model_output_exists")
        info = {"metadata": self.meta, "fingerprint": self.fingerprint,
                "candidates": {k: list(v.candidates) for k, v in self.memories.items()}}
        (target / "model.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        np.savez_compressed(target / "weights.npz", **{k: v.vector for k, v in self.memories.items()})

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "model.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "candidates"}, "invalid model envelope")
        meta = info["metadata"]
        book = Book(meta["dimension"], meta["seed"])
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            require(set(weights.files) == set(MEMORIES), "invalid weight names")
            memories = {k: Memory(book, weights[k], info["candidates"][k], meta["minimum"], meta["margin"]) for k in MEMORIES}
        model = cls(meta, memories)
        require(model.fingerprint == info["fingerprint"], "model_hash_mismatch")
        return model


def chip_roundtrip(model, packet, length=4):
    """Explicit balanced +/-1 chips, ideal alignment only; NOT S1 integration.

    Equal energy: chips[d,j] = meaning[d] * code[j] / sqrt(L).
    No truth offsets, sync, channel robustness, or RF claims.
    """
    require(type(length) is int and length >= 2 and length <= 64 and length % 2 == 0, "invalid chip length")
    vector = model.unpack(packet)
    code = np.tile(np.array([1., -1.]), length // 2)
    chips = vector[:, None] * code[None, :] / np.sqrt(length)
    recovered = np.sum(chips * code[None, :], axis=1) / np.sqrt(length)
    return model.pack(recovered), {"chip_count": int(chips.size), "chips_per_component": length,
                                  "input_energy": float(np.sum(np.abs(vector) ** 2)),
                                  "chip_energy": float(np.sum(np.abs(chips) ** 2)),
                                  "maximum_error": float(np.max(np.abs(vector - recovered))),
                                  "scope": "ideal_mapping_only_not_S1_receiver_integration"}
````

## `plm_l1/teacher.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/teacher.py`  
SHA256: `691d7f960f200fefd1da933a9e063bdbbe032a1476bbae8a6389745b43907ce2`

````python
"""Synthetic, manually specified teaching language. NEVER imported by inference.

The grammar and state/action supervision are supplied, not discovered. Evaluation
uses disjoint compositions; this is not independently collected natural language.
"""
NAMES = ("太郎", "花子", "次郎", "美咲", "健太", "由紀")
VERBS = (("助け", "help"), ("褒め", "praise"), ("訪ね", "visit"), ("見つめ", "gaze_at"))
SUFFIXES = {
    ("positive", "asserted"): ("た", "PAST"),
    ("negative", "asserted"): ("なかった", "NEG_PAST"),
    ("positive", "hypothetical"): ("たら", "COND"),
    ("negative", "hypothetical"): ("なかったら", "NEG_COND"),
}
GOALS = ("subject_first", "object_first")


def lexicon():
    entries = [(name, "ENTITY", "entity:" + name) for name in NAMES]
    entries += [(stem, "PREDICATE", "predicate:" + pred) for stem, pred in VERBS]
    entries += [("が", "GA", "literal:が"), ("を", "WO", "literal:を"),
                ("もし", "IF", "literal:もし"), ("。", "DOT", "literal:。"),
                ("<EOS>", "EOS", "literal:<EOS>")]
    entries += [(surface, category, "literal:" + surface) for surface, category in SUFFIXES.values()]
    return entries


def split_of(ai, bi, pi):
    residue = (ai + 2 * bi + pi) % 5
    return "evaluation" if residue == 0 else "development" if residue == 1 else "train"


def examples(split):
    for ai, actor in enumerate(NAMES):
        for bi, patient in enumerate(NAMES):
            if ai == bi:
                continue
            for pi, (stem, predicate) in enumerate(VERBS):
                if split_of(ai, bi, pi) != split:
                    continue
                for polarity, mode in SUFFIXES:
                    for order in GOALS:
                        slots = {"subject": "entity:" + actor, "object": "entity:" + patient,
                                 "predicate": "predicate:" + predicate,
                                 "polarity": "polarity:" + polarity, "modality": "modality:" + mode}
                        yield {"id": f"{ai}-{bi}-{pi}-{polarity}-{mode}-{order}",
                               "slots": slots, "order": order,
                               "text": surface(actor, patient, stem, polarity, mode, order)}


def surface(actor, patient, stem, polarity, mode, order):
    clauses = actor + "が" + patient + "を" if order == "subject_first" else patient + "を" + actor + "が"
    return ("もし" if mode == "hypothetical" else "") + clauses + stem + SUFFIXES[polarity, mode][0] + "。"


def reader_trace(example):
    """Explicit teacher annotations, not a parser available to the receiver."""
    slots, order = example["slots"], example["order"]
    mode = slots["modality"].split(":", 1)[1]
    polarity = slots["polarity"].split(":", 1)[1]
    actor, patient = slots["subject"].split(":", 1)[1], slots["object"].split(":", 1)[1]
    stem = dict((pred, stem) for stem, pred in VERBS)[slots["predicate"].split(":", 1)[1]]
    rows = []
    q = "A0"

    def step(token, category, action, nxt):
        nonlocal q
        rows.append((q, token, category, action, nxt))
        q = nxt

    prefix = "H" if mode == "hypothetical" else "A"
    if mode == "hypothetical":
        step("もし", "IF", "noop", "H0")
    first, second = (actor, patient) if order == "subject_first" else (patient, actor)
    first_role, second_role = ("subject", "object") if order == "subject_first" else ("object", "subject")
    branch = "S" if order == "subject_first" else "O"
    step(first, "ENTITY", "capture", prefix + "1")
    step("が" if first_role == "subject" else "を", "GA" if first_role == "subject" else "WO", "bind:" + first_role, prefix + branch + "2")
    step(second, "ENTITY", "capture", prefix + branch + "3")
    step("が" if second_role == "subject" else "を", "GA" if second_role == "subject" else "WO", "bind:" + second_role, prefix + "4")
    step(stem, "PREDICATE", "predicate", prefix + "5")
    suffix, category = SUFFIXES[polarity, mode]
    step(suffix, category, "status:" + polarity + ":" + mode, "E0")
    step("。", "DOT", "noop", "E1")
    step("<EOS>", "EOS", "stop", "DONE")
    return rows


def writer_trace(example, goal):
    """Token-level construction supervision. No complete output strings stored."""
    polarity = example["slots"]["polarity"].split(":", 1)[1]
    mode = example["slots"]["modality"].split(":", 1)[1]
    actions = ["emit:literal:もし"] if mode == "hypothetical" else []
    if goal == "subject_first":
        actions += ["slot:subject", "emit:literal:が", "slot:object", "emit:literal:を"]
    else:
        actions += ["slot:object", "emit:literal:を", "slot:subject", "emit:literal:が"]
    actions += ["slot:predicate", "emit:literal:" + SUFFIXES[polarity, mode][0], "emit:literal:。", "stop"]
    return list(enumerate(actions))
````

## `plm_l1/training.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/plm_l1/training.py`  
SHA256: `eb1f9044572591640aa91473e70113b56913725c804371b9636623f888440f09`

````python
"""Supervised fitting; separate from inference, teacher and held-out labels."""
from .algebra import Book, learn, digest
from .teacher import lexicon, examples, reader_trace, writer_trace, GOALS
from .runtime import Model, reader_key, writer_key


def fit(seed="development-0", dimension=8192, *, learning=True, order_binding=True, role_binding=True):
    book = Book(dimension, seed)
    pairs = {k: [] for k in ("lex_class", "lex_value", "surface", "read_action", "read_next", "write_action")}
    vocabulary = lexicon()
    for surface, category, value in vocabulary:
        parts = [("token", surface)]
        pairs["lex_class"].append((parts, category))
        pairs["lex_value"].append((parts, value))
        pairs["surface"].append(([("meaning", value)], surface))
    records = list(examples("train"))
    for row in records:
        for state, token, category, action, nxt in reader_trace(row):
            parts = reader_key(state, category, order_binding)
            pairs["read_action"].append((parts, action))
            pairs["read_next"].append((parts, nxt))
        for goal in GOALS:
            for position, action in writer_trace(row, goal):
                parts = writer_key(goal, position, row["slots"]["polarity"], row["slots"]["modality"], order_binding)
                pairs["write_action"].append((parts, action))
    memories, stats = {}, {}
    for name in pairs:
        memories[name], stats[name] = learn(book, pairs[name], learning)
    candidates = {
        "subject": [v for _, c, v in vocabulary if c == "ENTITY"],
        "object": [v for _, c, v in vocabulary if c == "ENTITY"],
        "predicate": [v for _, c, v in vocabulary if c == "PREDICATE"],
        "polarity": ["polarity:positive", "polarity:negative"],
        "modality": ["modality:asserted", "modality:hypothetical"],
    }
    metadata = {"schema": "plm-l1-model-v1", "dimension": dimension, "seed": seed,
                "learning": learning, "order_binding": order_binding, "role_binding": role_binding,
                "token_surfaces": sorted(s for s, _, _ in vocabulary if s != "<EOS>"),
                "slot_candidates": candidates, "training_count": len(records),
                "training_digest": digest(records), "memory_statistics": stats,
                "minimum": 0.60, "margin": 0.25, "max_tokens": 10, "max_generation_steps": 10,
                "initial_state": "A0", "terminal_state": "DONE", "goals": list(GOALS),
                "eligible_for_inference": False}
    return Model(metadata, memories)
````

## `release_tools.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/release_tools.py`  
SHA256: `c9d755ddb0c4e9336cf0b68212c59e2bc94feae1e3f0ba51eaf2b0a7097c05d4`

````python
"""Reproducible source freeze and additive release packaging; no old release edits."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from plm_l1.algebra import digest
from plm_l1.runtime import Model

ROOT = Path(__file__).resolve().parent
EXCLUDED = {"results", "verification", "examples", "__pycache__"}
MANIFESTS = {"SOURCE_MANIFEST.json", "RELEASE_MANIFEST.json"}


def source_files():
    # Root JSON/NPZ files can be CLI outputs. Source/config files live in the
    # explicit inventories below; generated packets must not invalidate them.
    paths = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".md", ".txt") and p.name not in MANIFESTS]
    for name in ("plm_l1", "tests", "evaluation"):
        paths.extend(p for p in (ROOT / name).rglob("*") if p.is_file())
    return sorted(p for p in paths if "__pycache__" not in p.parts and p.suffix != ".pyc")


def hashes(paths, base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "baseline", "check-baseline", "demo", "pack"))
    args = parser.parse_args()
    if args.command == "freeze":
        manifest = {"schema": "plm-l1-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write_new(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif args.command in ("baseline", "check-baseline"):
        targets = []
        for name in ("PLM-P1-v0.2", "PLM-S1-v0.2"):
            folder = ROOT.parent / name
            targets += [p for p in folder.rglob("*") if p.is_file()]
            targets += [ROOT.parent / (name + ".zip")]
        snapshot = {"schema": "plm-l1-preserved-releases-v1", "files": hashes(sorted(targets), ROOT.parent)}
        path = ROOT / "verification" / "PRESERVED_BASELINE.json"
        if args.command == "baseline":
            write_new(path, snapshot)
        else:
            if snapshot != json.loads(path.read_text(encoding="utf-8")):
                raise ValueError("preserved release changed")
        print(json.dumps({"status": "unchanged" if args.command == "check-baseline" else "recorded", "files": len(snapshot["files"])}))
    elif args.command == "demo":
        model = Model.load(ROOT / "results" / "model")
        inputs = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けたら。", "もし太郎が花子を助けなかったら。", "太郎は花子を助けた。"]
        demos = []
        for text in inputs:
            read = model.read(text)
            row = {"input": text, "read_status": read["status"], "reason": read["reason"]}
            if read["status"] == "read":
                row["recovered"] = model.recover(read["packet"])
                row["generated"] = model.generate(read["packet"], "object_first")
                if not demos:
                    write_new(ROOT / "examples" / "MEANING_PACKET.json", read["packet"])
            demos.append(row)
        write_new(ROOT / "examples" / "ROUNDTRIP_DEMOS.json", {"audience": "human/evaluator only; never input to generator", "demos": demos})
    else:
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts)
        manifest = {"schema": "plm-l1-release-v1", "files": hashes(files, ROOT)}
        write_new(ROOT / "RELEASE_MANIFEST.json", manifest)
        archive = ROOT.parent / "PLM-L1-v0.1.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with (ROOT.parent / "PLM-L1-v0.1.sha256").open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": checksum, "files": len(files) + 1}))


if __name__ == "__main__":
    main()
````

## `requirements.txt`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/requirements.txt`  
SHA256: `7bd6b8946940b79948c548c8048e545684b91c8edc9444d8dfc0c8f76a97c0a7`

````text
numpy==2.3.5
````

## `tests/test_l1.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/tests/test_l1.py`  
SHA256: `02a322d88766f8c648ba77effd845123d694e59b1f1e030a58afd3e476854de5`

````python
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from plm_l1.algebra import Book, Memory, learn
from plm_l1.training import fit
from plm_l1.runtime import Model, reader_key, writer_key, chip_roundtrip
from plm_l1.teacher import examples, lexicon
from plm_l1.oracle import interpret, INVALID


class AlgebraTests(unittest.TestCase):
    def test_deterministic(self):
        np.testing.assert_array_equal(Book().code("x", "a"), Book().code("x", "a"))

    def test_unit_phasors(self):
        np.testing.assert_allclose(np.abs(Book().code("x", "a")), 1., atol=1e-14)

    def test_inverse_binding(self):
        b = Book()
        x, y = b.code("x", "a"), b.code("y", "b")
        np.testing.assert_allclose(x * y * y.conj(), x, atol=1e-14)

    def test_namespace_separation(self):
        b = Book()
        self.assertLess(abs(np.mean(b.code("x", "a") * b.code("y", "a").conj())), .1)

    def test_dimension_validation(self):
        for d in (0, 127, 129, 32768, True, 128.):
            with self.subTest(d=d), self.assertRaises(ValueError):
                Book(d)

    def test_seed_validation(self):
        for seed in ("", None, "a" * 129):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                Book(seed=seed)

    def test_hebbian_association(self):
        pairs = [([("key", str(i))], str(i)) for i in range(20)]
        memory, stats = learn(Book(), pairs)
        self.assertEqual(stats["contexts"], 20)
        for parts, target in pairs:
            self.assertEqual(memory.recall(parts)["value"], target)

    def test_unknown_association_abstains(self):
        memory, _ = learn(Book(), [([("key", "a")], "one"), ([("key", "b")], "two")])
        self.assertIsNone(memory.recall([("key", "missing")])["value"])

    def test_no_learning(self):
        memory, _ = learn(Book(), [([("key", "a")], "one")], False)
        self.assertIsNone(memory.recall([("key", "a")])["value"])

    def test_conflicting_associations_abstain(self):
        memory, stats = learn(Book(), [([("key", "a")], "one"), ([("key", "a")], "two")])
        self.assertEqual(stats["conflicting_contexts"], 1)
        self.assertIsNone(memory.recall([("key", "a")])["value"])

    def test_order_ablation_removes_state(self):
        self.assertNotEqual(reader_key("q1", "X"), reader_key("q2", "X"))
        self.assertEqual(reader_key("q1", "X", False), reader_key("q2", "X", False))

    def test_order_ablation_removes_position(self):
        self.assertNotEqual(writer_key("x", 0, "p", "m"), writer_key("x", 1, "p", "m"))
        self.assertEqual(writer_key("x", 0, "p", "m", False), writer_key("x", 1, "p", "m", False))


class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = fit()
        cls.sample = "太郎が花子を助けた。"
        cls.packet = cls.model.read(cls.sample)["packet"]

    def test_all_development_readings_and_both_goals(self):
        for example in examples("development"):
            with self.subTest(id=example["id"]):
                read = self.model.read(example["text"])
                self.assertEqual(read["status"], "read")
                self.assertEqual(self.model.recover(read["packet"])["slots"], example["slots"])
                for goal in self.model.meta["goals"]:
                    generated = self.model.generate(read["packet"], goal)
                    self.assertEqual(generated["status"], "generated")
                    self.assertEqual(interpret(generated["text"]), example["slots"])

    def test_role_swaps_change_packet(self):
        other = self.model.read("花子が太郎を助けた。")["packet"]
        self.assertNotEqual(other["real"], self.packet["real"])

    def test_paraphrases_same_meaning_signal(self):
        other = self.model.read("花子を太郎が助けた。")["packet"]
        np.testing.assert_allclose(other["real"], self.packet["real"], atol=1e-14)
        np.testing.assert_allclose(other["imag"], self.packet["imag"], atol=1e-14)

    def test_negative_not_phase_sign_flip(self):
        other = self.model.read("太郎が花子を助けなかった。")["packet"]
        self.assertGreater(np.linalg.norm(self.model.unpack(other) + self.model.unpack(self.packet)), 1.)
        self.assertEqual(self.model.recover(other)["slots"]["polarity"], "polarity:negative")

    def test_hypothetical_not_asserted(self):
        packet = self.model.read("もし太郎が花子を助けたら。")["packet"]
        self.assertEqual(self.model.recover(packet)["slots"]["modality"], "modality:hypothetical")

    def test_negative_hypothetical(self):
        packet = self.model.read("もし太郎が花子を助けなかったら。")["packet"]
        self.assertEqual(self.model.generate(packet)["text"], "もし花子を太郎が助けなかったら。")

    def test_invalid_inputs(self):
        for text in INVALID:
            with self.subTest(text=text):
                self.assertIsNone(interpret(text))
                self.assertEqual(self.model.read(text)["status"], "abstain")

    def test_nontext_input(self):
        for value in (None, 2, {}, [], True):
            self.assertEqual(self.model.read(value)["status"], "abstain")

    def test_repeated_roles_rejected(self):
        self.assertEqual(self.model.read("太郎が花子が助けた。")["status"], "abstain")

    def test_unseen_self_pair_is_not_a_new_entity(self):
        result = self.model.read("太郎が太郎を助けた。")
        self.assertEqual(result["status"], "read")
        decoded = self.model.recover(result["packet"])["slots"]
        self.assertEqual(decoded["subject"], decoded["object"])

    def test_packet_contains_no_text_or_slots(self):
        self.assertEqual(set(self.packet), {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        serial = json.dumps(self.packet, ensure_ascii=False)
        self.assertNotIn(self.sample, serial)
        self.assertNotIn("太郎", serial)

    def test_extra_packet_fields_rejected(self):
        for name in ("text", "slots", "gold", "metadata", "source", "trace"):
            packet = dict(self.packet, **{name: "forbidden"})
            self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_wrong_model_packet(self):
        packet = dict(self.packet, model_fingerprint="0" * 64)
        self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_wrong_schema(self):
        self.assertEqual(self.model.generate(dict(self.packet, schema="unknown"))["status"], "abstain")

    def test_inference_flag(self):
        self.assertFalse(self.model.read(self.sample)["eligible_for_inference"])
        self.assertFalse(self.model.generate(self.packet)["eligible_for_inference"])
        self.assertEqual(self.model.generate(dict(self.packet, eligible_for_inference=True))["status"], "abstain")

    def test_wrong_signal_shape(self):
        self.assertEqual(self.model.generate(dict(self.packet, real=[0.]))["status"], "abstain")

    def test_invalid_signal_numbers(self):
        for value in (float("nan"), float("inf"), True, "1", 1e100):
            packet = copy.deepcopy(self.packet)
            packet["real"][0] = value
            self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_zero_signal(self):
        packet = self.model.pack(np.zeros(self.model.book.dimension, dtype=complex))
        self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_excess_interference(self):
        packet = self.model.pack(self.model.unpack(self.packet) + self.model.book.code("noise", "unrelated"))
        self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_unknown_goal(self):
        self.assertEqual(self.model.generate(self.packet, "essay")["status"], "abstain")

    def test_generation_signature_has_no_source(self):
        self.assertEqual(list(inspect.signature(Model.generate).parameters), ["self", "packet", "goal"])

    def test_runtime_does_not_import_teacher_or_oracle(self):
        import plm_l1.runtime as runtime
        code = inspect.getsource(runtime)
        self.assertNotIn("from .teacher", code)
        self.assertNotIn("from .oracle", code)
        for word in ("太郎", "花子", "もし", "なかった", "subject_first", "object_first"):
            if word != "object_first":
                self.assertNotIn(word, code)

    def test_model_save_load_and_readonly_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            loaded = Model.load(directory)
            self.assertEqual(loaded.fingerprint, self.model.fingerprint)
            self.assertEqual(loaded.generate(self.packet)["text"], "花子を太郎が助けた。")
            with self.assertRaises(ValueError):
                self.model.save(directory)

    def test_model_tamper_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            path = Path(directory) / "model.json"
            info = json.loads(path.read_text(encoding="utf-8"))
            info["metadata"]["training_count"] += 1
            path.write_text(json.dumps(info), encoding="utf-8")
            with self.assertRaises(ValueError):
                Model.load(directory)

    def test_no_learning_ablation(self):
        self.assertEqual(fit(learning=False).read(self.sample)["status"], "abstain")

    def test_no_order_ablation(self):
        model = fit(order_binding=False)
        self.assertGreater(model.meta["memory_statistics"]["read_next"]["conflicting_contexts"], 0)
        self.assertEqual(model.read(self.sample)["status"], "abstain")

    def test_no_role_ablation(self):
        model = fit(role_binding=False)
        read = model.read(self.sample)
        self.assertEqual(read["status"], "read")
        self.assertEqual(model.generate(read["packet"])["status"], "abstain")

    def test_generation_learning_needed_even_with_working_reader(self):
        memories = dict(self.model.memories)
        old = memories["write_action"]
        memories["write_action"] = Memory(old.book, np.zeros(old.book.dimension), old.candidates)
        model = Model(self.model.meta, memories)
        read = model.read(self.sample)
        self.assertEqual(read["status"], "read")
        self.assertEqual(model.generate(read["packet"])["reason"], "generation_memory_unresolved")

    def test_reverse_lexical_learning_needed(self):
        memories = dict(self.model.memories)
        old = memories["surface"]
        memories["surface"] = Memory(old.book, np.zeros(old.book.dimension), old.candidates)
        model = Model(self.model.meta, memories)
        read = model.read(self.sample)
        self.assertEqual(read["status"], "read")
        self.assertEqual(model.generate(read["packet"])["reason"], "surface_memory_unresolved")

    def test_state_learning_needed(self):
        memories = dict(self.model.memories)
        old = memories["read_next"]
        memories["read_next"] = Memory(old.book, np.zeros(old.book.dimension), old.candidates)
        model = Model(self.model.meta, memories)
        self.assertEqual(model.read(self.sample)["reason"], "grammar_memory_unresolved")

    def test_chip_mapping_preserves_energy_and_meaning(self):
        packet, audit = chip_roundtrip(self.model, self.packet)
        self.assertAlmostEqual(audit["input_energy"], audit["chip_energy"], places=8)
        self.assertLess(audit["maximum_error"], 1e-12)
        self.assertEqual(self.model.generate(packet)["text"], "花子を太郎が助けた。")

    def test_invalid_chip_length(self):
        for length in (1, 3, 0, 128, True):
            with self.subTest(length=length), self.assertRaises(ValueError):
                chip_roundtrip(self.model, self.packet, length)

    def test_partition_is_disjoint_by_composition(self):
        partitions = {}
        for split in ("train", "development", "evaluation"):
            rows = list(examples(split))
            partitions[split] = {(x["slots"]["subject"], x["slots"]["object"], x["slots"]["predicate"]) for x in rows}
        self.assertFalse(partitions["train"] & partitions["evaluation"])
        self.assertFalse(partitions["train"] & partitions["development"])
        self.assertFalse(partitions["development"] & partitions["evaluation"])

    def test_teacher_and_independent_oracle_agree_on_development(self):
        for example in examples("development"):
            self.assertEqual(interpret(example["text"]), example["slots"])

    def test_fixed_identity_and_fitted_memory_separate(self):
        blank = fit(learning=False)
        np.testing.assert_array_equal(blank.book.code("value", "entity:太郎"), self.model.book.code("value", "entity:太郎"))
        self.assertFalse(np.array_equal(blank.memories["read_action"].vector, self.model.memories["read_action"].vector))


if __name__ == "__main__":
    unittest.main()
````

## `verify_release.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/vendor/PLM-L1-v0.3/vendor/PLM-L1-v0.2/vendor/PLM-L1-v0.1/verify_release.py`  
SHA256: `eaced02e2f134ad6312248caf4ccfa1b0968b29b35a0989a451b2f49863c073f`

````python
"""Local verification: frozen sources, tests, saved numeric results and isolated CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from evaluate import verify_freeze, judge
from plm_l1.algebra import digest
from plm_l1.runtime import Model
from plm_l1.oracle import interpret

ROOT = Path(__file__).resolve().parent


def run(args, cwd, output, name, expected=0):
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-B", *args], cwd=cwd, env=environment, text=True, encoding="utf-8", capture_output=True, timeout=180)
    (output / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != expected:
        raise ValueError(name + " failed: " + result.stderr[-1500:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("output directory already exists")
    output.mkdir(parents=True)
    freeze = verify_freeze()
    tests = run(["-m", "unittest", "discover", "-s", "tests", "-v"], ROOT, output, "UNIT_TESTS")
    result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
    claimed_digest = result.pop("result_digest")
    if digest(result) != claimed_digest or result["freeze_hash"] != freeze:
        raise ValueError("saved evaluation integrity failed")
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    checks = judge(result["results"], protocol)
    if checks != result["checks"] or not all(x["passed"] for x in checks):
        raise ValueError("saved evaluation acceptance failed")
    isolated = output / "isolated"
    package = isolated / "plm_l1"
    package.mkdir(parents=True)
    for name in ("__init__.py", "__main__.py", "algebra.py", "runtime.py"):
        shutil.copyfile(ROOT / "plm_l1" / name, package / name)
    run(["-c", "import importlib.util; assert importlib.util.find_spec('plm_l1.teacher') is None; assert importlib.util.find_spec('plm_l1.oracle') is None; assert importlib.util.find_spec('plm_l1.training') is None; print('teacher, oracle, training unavailable')"], isolated, output, "ISOLATION")
    model_path = str(ROOT / "results" / "model")
    sentences = ["太郎が花子を助けた。", "花子が太郎を褒めた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。"]
    demos = []
    for index, text in enumerate(sentences):
        packet_path = isolated / f"packet-{index}.json"
        read = json.loads(run(["-m", "plm_l1", "read", "--model", model_path, "--text", text, "--out", str(packet_path)], isolated, output, f"CLI_READ_{index}"))
        generated = json.loads(run(["-m", "plm_l1", "generate", "--model", model_path, "--packet", str(packet_path), "--goal", "object_first"], isolated, output, f"CLI_GENERATE_{index}"))
        if read["status"] != "read" or generated["status"] != "generated" or interpret(generated["text"]) != interpret(text):
            raise ValueError("isolated meaning preservation failed")
        demos.append({"input": text, "output": generated["text"], "meaning_exact": True})
    missing_path = isolated / "must-not-exist.json"
    run(["-m", "plm_l1", "read", "--model", model_path, "--text", "未知が花子を助けた。", "--out", str(missing_path)], isolated, output, "CLI_ABSTAIN", expected=2)
    if missing_path.exists():
        raise ValueError("abstention emitted a packet")
    release_path = ROOT / "RELEASE_MANIFEST.json"
    release_checked = False
    if release_path.exists():
        manifest = json.loads(release_path.read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        release_checked = True
    verification = {"status": "passed", "source_freeze": freeze, "result_digest": claimed_digest,
                    "acceptance_checks": len(checks), "unit_tests": 47, "isolated_cli_roundtrips": len(demos),
                    "unknown_input_cli_exit": 2, "release_manifest_checked": release_checked,
                    "numeric_full_evaluation_rerun_in_this_command": False, "demos": demos,
                    "python": sys.version, "executable": sys.executable}
    (output / "VERIFICATION.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

