# PLM-L1-v0.4 全コード（当該版直下・vendor重複除外）

原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。

## `evaluate.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/evaluate.py`  
SHA256: `b36f17c896a23aafb28a7cf5ebbcef99ce368a873f8adc82fc2313de19fb56a1`

````python
"""Frozen four-fold compositional holdout evaluation, all models refitted."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from plm_l1_v04.algebra import canonical, digest
from plm_l1_v04.training import fit
from evaluation_support import ROOT, FOLDS, data, train_for, heldout, text_goal, interpret, INVALID, GOALS, OldSS, PartialTable, OldTable


def source_files():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py",".md",".txt")]
    for name in ("plm_l1_v04","tests","evaluation","data","vendor"):
        files += [p for p in (ROOT/name).rglob("*") if p.is_file()]
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix!=".pyc")


def verify_freeze():
    manifest=json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    if actual!=manifest["files"]:
        raise ValueError("frozen source changed")
    return digest(manifest)


def bad_packets(model,meaning):
    p=model.encode(meaning)
    key="model_fingerprint" if "model_fingerprint" in p else "writer_fingerprint"
    n=p["dimension"]
    result=[dict(p,text="hidden source"),dict(p,meaning=meaning),dict(p,**{key:"bad"}),dict(p,dimension=0),
            dict(p,eligible_for_inference=True),dict(p,real=[0.]*n,imag=[0.]*n)]
    for value in (float("nan"),float("inf"),True,"1",1e100):
        q=copy.deepcopy(p)
        q["real"][0]=value
        result.append(q)
    result.append(dict(p,real=p["real"][:-1]))
    return result


def assess(model,split,fold,numeric=True):
    counts={}
    records=[]
    def add(stage,bucket,exact,accepted,record):
        for suffix,value in (("requests",1),("exact",int(exact)),("accepted",int(accepted)),("wrong",int(accepted and not exact))):
            k=stage+"_"+bucket+"_"+suffix
            counts[k]=counts.get(k,0)+value
        records.append({"stage":stage,"bucket":bucket,**record})
    rows=data(split)
    meanings={canonical(r["meaning"]):r["meaning"] for r in rows}
    for key in sorted(meanings):
        meaning=meanings[key]
        packet=model.encode(meaning)
        for goal in GOALS:
            out=model.generate(packet,goal)
            bucket="heldout" if heldout(meaning,goal,fold) else "seen"
            exact=out["status"]=="generated" and interpret(out["text"])==meaning and text_goal(out["text"])==goal
            add("generate",bucket,exact,out["status"]=="generated",{"expected":meaning,"goal":goal,"output":out.get("text"),"status":out["status"],"reason":out.get("reason")})
    for row in rows:
        read=model.read(row["text"])
        bucket="heldout" if heldout(row["meaning"],text_goal(row["text"]),fold) else "seen"
        meaning=model.recover(read["packet"]).get("meaning") if read["status"]=="read" else None
        add("read",bucket,meaning==row["meaning"],read["status"]=="read",{"input":row["text"],"expected":row["meaning"],"recovered":meaning,"status":read["status"],"reason":read.get("reason")})
        for goal in GOALS:
            # No gold meaning or original text enters the generator in this path.
            out=model.generate(read["packet"],goal) if read["status"]=="read" else {"status":"abstain","reason":"reader_abstained"}
            group="both_heldout" if bucket=="heldout" and heldout(row["meaning"],goal,fold) else "other"
            exact=out["status"]=="generated" and interpret(out["text"])==row["meaning"] and text_goal(out["text"])==goal
            add("roundtrip",group,exact,out["status"]=="generated",{"input_for_evaluator_only":row["text"],"expected":row["meaning"],"goal":goal,"output":out.get("text"),"status":out["status"],"reason":out.get("reason")})
    counts["invalid_texts"]=len(INVALID)
    counts["invalid_texts_accepted"]=sum(model.read(text)["status"]=="read" for text in INVALID)
    packets=bad_packets(model,next(iter(meanings.values()))) if numeric else []
    counts["invalid_packets"]=len(packets)
    counts["invalid_packets_generated"]=sum(model.generate(p)["status"]=="generated" for p in packets)
    return {"counts":counts,"records":records,"fingerprint":model.fingerprint,"training_pairs":model.meta["pair_count"],"statistics":model.meta["statistics"]}


def one(seed,fold,condition,dimension,split):
    pairs,lexicon=train_for(fold),data("lexicon")
    if condition=="old_ss":
        model=OldSS(pairs,lexicon,seed,dimension)
    else:
        model=fit(pairs,lexicon,seed=seed,dimension=dimension,partial=condition!="full_context",learning=condition!="no_learning")
    result=assess(model,split,fold)
    result.update(seed=seed,fold=fold,condition=condition,dimension=dimension)
    return result,model


def judge(rows,protocol,regressions=()):
    checks=[]
    for fold in protocol["folds"]:
        for seed in protocol["evaluation_seeds"]:
            variants={r["condition"]:r["counts"] for r in rows if r["fold"]==fold and r["seed"]==seed}
            full=variants["partial"]
            values={}
            for key in ("read_heldout","read_seen","generate_heldout","generate_seen","roundtrip_both_heldout","roundtrip_other"):
                values[key]=full[key+"_exact"]/full[key+"_requests"]>=.98
            values["no_wrong"]=sum(v for k,v in full.items() if k.endswith("_wrong"))==0
            values["invalid_boundaries"]=full["invalid_texts_accepted"]+full["invalid_packets_generated"]==0
            for condition in ("full_context","old_ss"):
                c=variants[condition]
                values[condition+"_seen_control"]=all(c[s+"_seen_exact"]/c[s+"_seen_requests"]>=.98 for s in ("read","generate"))
                values[condition+"_novelty_drop"]=all(full[s+"_heldout_exact"]/full[s+"_heldout_requests"]-c[s+"_heldout_exact"]/c[s+"_heldout_requests"]>=.50 for s in ("read","generate"))
            c=variants["no_learning"]
            values["learning_required"]=sum(v for k,v in c.items() if k.endswith("_accepted") and k not in ("invalid_texts_accepted",))==0
            checks += [{"fold":fold,"seed":seed,"name":name,"passed":bool(value)} for name,value in values.items()]
    if regressions:
        c=regressions[0]["counts"]
        full_correct=all(c[s+"_"+b+"_exact"]==c[s+"_"+b+"_requests"] for s,b in (("read","seen"),("read","heldout"),("generate","seen"),("generate","heldout"),("roundtrip","other"),("roundtrip","both_heldout")))
        checks.append({"fold":"all","seed":"regression","name":"full_training_regression","passed":full_correct and c["invalid_texts_accepted"]+c["invalid_packets_generated"]==0})
    return checks


def report(output,result):
    result["result_digest"]=digest(result)
    (output/"EVALUATION.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    totals={}
    for r in result["results"]:
        counts=totals.setdefault(r["condition"],{k:0 for k in r["counts"]})
        for k,v in r["counts"].items():
            counts[k]+=v
    def ratio(c,key):
        return str(c[key+"_exact"])+"/"+str(c[key+"_requests"])
    lines=["# PLM-L1 v0.4 評価結果","","4種類の語順×肯否の組合せを1つずつ丸ごと学習から除外。各モデルは同じ432対から再学習。", "",
           "| 方式 | 未学習組合せ 読解 | 未学習組合せ 生成単体 | 読解・生成とも未学習組合せ | 既出組合せ 読解/生成 | 誤受理・誤出力 |",
           "|---|---:|---:|---:|---:|---:|"]
    for name,c in totals.items():
        wrong=sum(v for k,v in c.items() if k.endswith("_wrong"))+c["invalid_texts_accepted"]+c["invalid_packets_generated"]
        lines.append(f"| {name} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} | {ratio(c,'read_seen')} / {ratio(c,'generate_seen')} | {wrong} |")
    lines += ["",f"受入：{sum(c['passed'] for c in result['checks'])}/{len(result['checks'])}、合格判定：{result['passed']}。", "",
              "partialは学習した部分手掛かりで照合。full_contextは同じ断片分割だが照会の全特徴を必要とする比較。old_ssはv0.2読解器とv0.3生成器を同じ制限データで再学習。no_learningは語彙以外の連想重みを無効化。保留は成功に数えない。",
              "", "## 表引き比較（各foldに1回、符号反復なし）", "", "| fold | 方式 | 未学習 読解 | 未学習 生成 | 未学習 往復 |", "|---|---|---:|---:|---:|"]
    for r in result["references"]:
        c=r["counts"]
        lines.append(f"| {r['fold']} | {r['condition']} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} |")
    lines += ["", "部分手掛かりを使う表引きも同じ自動特徴選択と断片分割を使う。数値符号は用いない。この比較は分解と共有の寄与を区別するためで、SSの速度・容量・省電力優位性を示すものではない。", "",
              "## 低次元ストレス（非合否）", "", "| seed | 次元 | 未学習 読解 | 未学習 生成 | 未学習 往復 | 誤受理・誤出力 |", "|---|---:|---:|---:|---:|---:|"]
    for r in result["stress"]:
        c=r["counts"]
        wrong=sum(v for k,v in c.items() if k.endswith("_wrong"))+c["invalid_texts_accepted"]+c["invalid_packets_generated"]
        lines.append(f"| {r['seed']} | {r['dimension']} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} | {wrong} |")
    lines += ["", "## 全学習データでの回帰", ""]
    for r in result["regressions"]:
        c=r["counts"]
        lines.append(f"576対をすべて学習した新方式：読解 {c['read_seen_exact']+c['read_heldout_exact']}/{c['read_seen_requests']+c['read_heldout_requests']}、生成単体 {c['generate_seen_exact']+c['generate_heldout_exact']}/{c['generate_seen_requests']+c['generate_heldout_requests']}。このモデルを組合せ除外試験には用いていない。")
    lines += ["", "## 主張の境界", "", "評価には既存192文を再利用する。各foldで未学習組合せ48、既出組合せ144。4fold×4符号の反復であり、独立した新規自然文コーパスではない。語・語義・構文要素は既知で、初めてなのはそのモデルの学習から除いた語順×肯否の組合せ。",
              "", "手設計の分解は『内容語の役割順序＋その間のmarker列』。依存特徴の選択は通常の情報利得による分類処理で学び、学習された対応を位相連想記憶に保存・相関照合する。全学習処理のSS化や構文部品の無制約な発見ではない。",
              "", "v0.3の次語自己回帰から、学習した役割順序と記号列部品を組み立てる生成へ変更した。記号列部品には語尾と句点をまとめた断片も含まれる。任意の階層・新語義・長文・自由作文は対象外。",
              "", "読解と生成は共通の断片記憶を利用するため、往復だけで評価せず、各単体を別実装の限定文法で採点する。原文や正解意味を生成側へ渡すのは禁じるが、生成単体試験は定義上正解意味を入力する。",
              "", "今回の部分照合は文脈特徴の射影。P1の観測数値成分マスク/干渉除去の統合ではない。Phase/VSA領域であり、S1の明示チップ同期統合・R1推論開放・Concept更新は行っていない。", "",
              f"結果digest：`{result['result_digest']}`",f"ソース固定digest：`{result['freeze_hash']}`",""]
    (output/"EVALUATION_REPORT.md").write_text("\n".join(lines),encoding="utf-8")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--development",action="store_true")
    args=parser.parse_args()
    output=Path(args.out)
    if output.exists():
        raise ValueError("fresh output required")
    freeze="development_not_frozen" if args.development else verify_freeze()
    protocol=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    split="development" if args.development else "evaluation"
    seeds=protocol["development_seeds"] if args.development else protocol["evaluation_seeds"]
    results=[]
    for fold in protocol["folds"]:
        for seed in seeds:
            for condition in protocol["conditions"]:
                row,model=one(seed,fold,condition,protocol["dimension"],split)
                results.append(row)
                print(json.dumps({"fold":fold,"seed":seed,"condition":condition,"counts":row["counts"]}),flush=True)
                if fold==protocol["folds"][0] and seed==seeds[0] and condition=="partial":
                    model.save(output/"model")
    references=[]
    for fold in protocol["folds"]:
        for name,cls in (("partial_table",PartialTable),("old_whole_table",OldTable)):
            r=assess(cls(train_for(fold),data("lexicon")),split,fold,numeric=False)
            r.update(fold=fold,condition=name)
            references.append(r)
    stress=[]
    if not args.development:
        for seed in protocol["stress_seeds"]:
            for dimension in protocol["stress_dimensions"]:
                r,_=one(seed,protocol["folds"][0],"partial",dimension,split)
                stress.append(r)
                print(json.dumps({"stress":seed,"dimension":dimension,"counts":r["counts"]}),flush=True)
    regressions=[]
    model=fit(data("train"),data("lexicon"),seed="parts-full-regression-0")
    regressions.append(assess(model,split,protocol["folds"][0]))
    checks=[] if args.development else judge(results,protocol,regressions)
    result={"schema":"plm-l1-v04-results-v1","freeze_hash":freeze,"results":results,"references":references,"stress":stress,"regressions":regressions,
            "checks":checks,"passed":bool(checks) and all(c["passed"] for c in checks)}
    report(output,result)
    print("RESULT_DIGEST "+result["result_digest"],flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
````

## `evaluation_support.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/evaluation_support.py`  
SHA256: `4587960402424ebb3c7e1b6c39cdb1c335cb072fc522614dae1fec3f6d42b046`

````python
"""Evaluator-only splits, independent language scoring, and matched baselines."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from plm_l1_v04.algebra import canonical, digest
from plm_l1_v04.lexicon import aligned_examples, GOALS
from plm_l1_v04.features import observations
from plm_l1_v04.projection import dependency_leaves
from plm_l1_v04.runtime import Model

ROOT = Path(__file__).resolve().parent
V03 = ROOT / "vendor" / "PLM-L1-v0.3"
V02 = V03 / "vendor" / "PLM-L1-v0.2"
for path in (V03, V02, V02 / "vendor" / "PLM-L1-v0.1"):
    if str(path) not in sys.path:
        # unittest may place tests/ at index 0; append legacy packages so their
        # same-named evaluator scripts cannot shadow this release's scripts.
        sys.path.append(str(path))
from plm_l1.oracle import interpret, INVALID, PATTERNS

FOLDS = ("object_negative", "subject_negative", "object_positive", "subject_positive")


def data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def text_goal(text):
    return next(("subject" if i == 0 else "object" for i, p in enumerate(PATTERNS) if p.fullmatch(text)), None)


def heldout(meaning, goal, fold):
    order, polarity = fold.split("_")
    return goal == order and meaning["polarity"] == "polarity:" + polarity


def train_for(fold):
    return data("folds/" + fold + "/train")


def normalize_markers(text, mapping):
    for a in sorted(mapping, key=lambda x: (-len(x), x)):
        text = text.replace(a, mapping[a])
    return text


def opaque(pairs, lexicon):
    pairs, lexicon = copy.deepcopy(pairs), copy.deepcopy(lexicon)
    mapping = {s: f"~M{i}~" for i,s in enumerate(sorted(t["surface"] for t in lexicon["tokens"] if t["kind"] == "marker"))}
    for row in pairs:
        row["text"] = normalize_markers(row["text"], mapping)
    for token in lexicon["tokens"]:
        if token["kind"] == "marker":
            token["surface"] = mapping[token["surface"]]
    return pairs, lexicon, mapping


class OldSS:
    """v0.2 reader and v0.3 writer BOTH retrained on the same restricted pairs."""
    def __init__(self, pairs, lexicon, seed, dimension=8192):
        from plm_l1_v02.training import fit as fit_reader
        from plm_l1_v03.training import fit as fit_writer
        self.reader = fit_reader(pairs, lexicon, seed=seed, dimension=dimension)
        self.writer = fit_writer(pairs, lexicon, seed=seed, dimension=dimension)
        self.fingerprint = digest([self.reader.fingerprint, self.writer.fingerprint])
        self.meta = {"pair_count": len(pairs), "statistics": {"reader": self.reader.meta["statistics"], "writer": self.writer.meta["statistics"]}}

    def read(self, text):
        r = self.reader.read(text)
        if r["status"] != "read":
            return r
        meaning = self.reader.recover(r["packet"])
        if meaning["status"] != "recovered":
            return {"status": "abstain", "reason": "old_meaning_recovery_failed"}
        return {"status": "read", "packet": self.writer.encode(meaning["slots"])}

    def encode(self, meaning):
        return self.writer.encode(meaning)

    def recover(self, packet):
        return self.writer.recover(packet)

    def generate(self, packet, goal="object"):
        return self.writer.generate(packet, goal)


class DictMemory:
    def __init__(self, observations):
        self.leaves = dependency_leaves(observations, True)

    def recall(self, context):
        labels = {label for key, label in self.leaves if all(context.get(k) == v for k,v in key.items())}
        return {"value": next(iter(labels)) if len(labels) == 1 else None}


class PartialTable(Model):
    """Same learned projections/components, but ordinary matching, no phase codec."""
    def __init__(self, pairs, lexicon):
        rows = observations(pairs, lexicon)
        self.memories = {name: DictMemory(row) for name, row in rows.items()}
        self.meta = {"kinds": {t["surface"]:t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"], "pair_count": len(pairs), "statistics": {}}
        self.fingerprint = digest(["partial_table", pairs, lexicon])

    def encode(self, meaning):
        return {"meaning": dict(meaning)}

    def recover(self, packet):
        return {"status": "recovered", "meaning": dict(packet["meaning"])}


def helper(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OldTable(PartialTable):
    def __init__(self, pairs, lexicon):
        self.reader = helper(V02 / "evaluation_support.py", "old_reader_tables").LookupReader(pairs, lexicon)
        self.writer = helper(V03 / "evaluation_support.py", "old_writer_tables").LookupWriter(pairs, lexicon)
        self.fingerprint = digest(["whole_context_table", pairs, lexicon])
        self.meta = {"pair_count":len(pairs), "statistics":{}}

    def read(self, text):
        meaning = self.reader.read(text)
        return {"status":"read", "packet":self.encode(meaning)} if meaning is not None else {"status":"abstain", "reason":"unknown_whole_context"}

    def generate(self, packet, goal="object"):
        text = self.writer.generate(packet["meaning"], goal)
        return {"status":"generated" if text is not None else "abstain", "text":text, "reason":None if text is not None else "unknown_prefix"}
````

## `plm_l1_v04/__init__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/__init__.py`  
SHA256: `8650a909c80217727c2f30ede90989184ee0efd537cc69af5f036879d88c6121`

````python
"""PLM-L1 0.4.0: learned partial-context component reuse."""
__version__ = "0.4.0"
````

## `plm_l1_v04/__main__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/__main__.py`  
SHA256: `12387937128ac55765e9ffb92871235c0df08ab23bba3eb088d6193d9ea44413`

````python
import argparse
import json
from pathlib import Path
from .runtime import Model


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    fit = commands.add_parser("train")
    fit.add_argument("--pairs", required=True)
    fit.add_argument("--lexicon", required=True)
    fit.add_argument("--out", required=True)
    fit.add_argument("--seed", default="parts-development-0")
    fit.add_argument("--dimension", type=int, default=8192)
    for name in ("read", "encode", "generate"):
        p = commands.add_parser(name)
        p.add_argument("--model", required=True)
        if name == "generate":
            p.add_argument("--packet", required=True)
            p.add_argument("--goal", choices=("subject", "object"), default="object")
        else:
            p.add_argument("--text" if name == "read" else "--meaning", required=True)
            p.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "train":
            from .training import fit
            model = fit(load(args.pairs), load(args.lexicon), seed=args.seed, dimension=args.dimension)
            model.save(args.out)
            result = {"status": "trained", "fingerprint": model.fingerprint, "pair_count": model.meta["pair_count"], "statistics": model.meta["statistics"]}
        else:
            model = Model.load(args.model)
            if args.command == "read":
                result = model.read(args.text)
                if result["status"] == "read":
                    write(args.out, result.pop("packet"))
            elif args.command == "encode":
                write(args.out, model.encode(load(args.meaning)))
                result = {"status": "encoded"}
            else:
                result = model.generate(load(args.packet), args.goal)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result["status"] == "abstain" else 0
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
````

## `plm_l1_v04/algebra.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/algebra.py`  
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

## `plm_l1_v04/features.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/features.py`  
SHA256: `58ecd03848729604f26301be44691fd584d1905a442febaf40a006eb7032a5cc`

````python
"""Designed, language-neutral decomposition into content order and marker gaps."""
from .algebra import canonical, require
from .lexicon import CONTENT, ROLES, GOALS, tokenize, aligned_examples

START = "start"


def abstract_token(token, kinds):
    return ["marker", token] if kinds[token] == "marker" else ["kind", kinds[token]]


def shape(tokens, kinds):
    return [abstract_token(t, kinds) for t in tokens]


def role_context(tokens, position, kinds):
    return {"kind": kinds[tokens[position]],
            "left": abstract_token(tokens[position - 1], kinds) if position else ["boundary", "start"],
            "right": abstract_token(tokens[position + 1], kinds) if position + 1 < len(tokens) else ["boundary", "end"],
            "whole_shape": shape(tokens, kinds)}


def split_gaps(tokens, positions):
    # positions maps content-token indices to their inferred semantic roles.
    gaps, order, anchor = {START: []}, [], START
    for i, token in enumerate(tokens):
        if i in positions:
            anchor = positions[i]
            require(anchor in CONTENT and anchor not in gaps, "duplicate_role")
            order.append(anchor)
            gaps[anchor] = []
        else:
            gaps[anchor].append(token)
    require(set(order) == set(CONTENT) and len(order) == len(CONTENT), "incomplete_content")
    return order, gaps


def status_context(tokens, kinds, gaps, order):
    return {"leading_markers": gaps[START], "subject_markers": gaps["subject"],
            "object_markers": gaps["object"], "predicate_markers": gaps["predicate"],
            "content_order": order, "whole_shape": shape(tokens, kinds)}


def gap_context(meaning, goal, anchor):
    return {"anchor": anchor, "polarity": meaning["polarity"], "modality": meaning["modality"], "goal": goal}


def observations(pairs, lexicon):
    examples = aligned_examples(pairs, lexicon)
    kinds = {t["surface"]: t["kind"] for t in lexicon["tokens"]}
    values = {t["surface"]: t["value"] for t in lexicon["tokens"]}
    rows = {name: [] for name in ("roles", "polarity", "modality", "order_support", "order_output", "gaps", "lexical_read", "lexical_write")}
    for pair, example in zip(pairs, examples):
        tokens = tokenize(pair["text"], kinds)
        meaning = pair["meaning"]
        positions = {}
        for i, token in enumerate(tokens):
            if kinds[token] != "marker":
                role = next(r for r in CONTENT if meaning[r] == values[token])
                positions[i] = role
                rows["roles"].append((role_context(tokens, i, kinds), role))
        order, gaps = split_gaps(tokens, positions)
        goal = order[0]
        context = status_context(tokens, kinds, gaps, order)
        for slot in ("polarity", "modality"):
            rows[slot].append((context, meaning[slot]))
        rows["order_support"].append(({"order": order}, "supported"))
        rows["order_output"].append(({"goal": goal}, canonical(order)))
        for anchor, gap in gaps.items():
            rows["gaps"].append((gap_context(meaning, goal, anchor), canonical(gap)))
    for token in lexicon["tokens"]:
        if token["kind"] != "marker":
            rows["lexical_read"].append(({"surface": token["surface"]}, token["value"]))
            rows["lexical_write"].append(({"meaning_value": token["value"]}, token["surface"]))
    return rows
````

## `plm_l1_v04/lexicon.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/lexicon.py`  
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

## `plm_l1_v04/projection.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/projection.py`  
SHA256: `3309fb4de269d3aba62311a98c9bc067975182f9be113968c02f94b06c8312b8`

````python
"""Train-only categorical dependency selection, phase-only leaf lookup.

The dependency selector is conventional symbolic training machinery. At runtime
no tree, leaf feature values, or key->target table are retained. Learned masks
and candidate inventories are public model metadata; decisions use correlation.
"""
import json
import math
from collections import Counter
import numpy as np
from .algebra import canonical, require


def structure_code(book, value, domain="target"):
    if isinstance(value, list):
        out = book.code("sequence_length:" + domain, len(value)).copy()
        for i, item in enumerate(value):
            out *= np.roll(structure_code(book, item, domain + "/item:" + str(i)), 17 * i)
        return out
    return book.code("atom:" + domain, value)


class Space:
    def __init__(self, book):
        self.book, self.cache = book, {}

    def key(self, fields):
        identity = canonical(fields)
        if identity not in self.cache:
            out = self.book.code("field_set", sorted(fields)).copy()
            for field in sorted(fields):
                # Values are encoded in field-specific namespaces. Multiplying
                # an independent field code and a shared value code would lose
                # assignments when values are swapped between two fields.
                out *= structure_code(self.book, fields[field], "field:" + field)
            self.cache[identity] = out
        return self.cache[identity]

    def target(self, label):
        try:
            value = json.loads(label)
        except (json.JSONDecodeError, TypeError):
            value = label
        return self.book.code("target_namespace", "target") * structure_code(self.book, value)


def dependency_leaves(observations, partial=True):
    """Deterministic ID3-style partition on deduplicated context/target pairs.

    Information gain, then smaller arity and canonical field name break ties.
    Leaf conjunctions become partial projection associations, not runtime rules.
    """
    require(type(partial) is bool and bool(observations), "invalid_observations")
    unique = {}
    fields = set(observations[0][0])
    for context, label in observations:
        require(set(context) == fields and type(label) is str, "invalid_context_schema")
        key = canonical(context)
        require(key not in unique or unique[key][1] == label, "conflicting_complete_context")
        unique[key] = (context, label)
    rows = [unique[k] for k in sorted(unique)]
    if not partial:
        return rows

    def entropy(part):
        counts = Counter(label for _, label in part)
        return -sum((n / len(part)) * math.log2(n / len(part)) for n in counts.values())

    def visit(part, remaining, path):
        if len({label for _, label in part}) == 1:
            # Positive-only support is not evidence for universal support.
            return [(dict(path), part[0][1])] if path else part
        require(bool(remaining), "unresolved_labels")
        options = []
        for field in sorted(remaining):
            groups = {}
            for context, label in part:
                groups.setdefault(canonical(context[field]), []).append((context, label))
            if len(groups) < 2:
                continue
            gain = entropy(part) - sum(len(group) / len(part) * entropy(group) for group in groups.values())
            options.append((-round(gain, 12), len(groups), field, groups))
        require(bool(options), "no_dependency_split")
        _, _, field, groups = min(options, key=lambda row: row[:3])
        result = []
        for key in sorted(groups):
            result += visit(groups[key], remaining - {field}, dict(path, **{field: json.loads(key)}))
        return result
    return visit(rows, fields, {})


class ProjectionMemory:
    def __init__(self, space, groups):
        self.space, self.groups, self.cache = space, [], {}
        for mask, vector, candidates in groups:
            mask = tuple(mask)
            vector = np.asarray(vector, dtype=np.complex128).copy()
            require(vector.shape == (space.book.dimension,) and np.isfinite(vector).all(), "invalid_weights")
            candidates = tuple(sorted(set(candidates)))
            require(bool(candidates), "empty_candidates")
            basis = np.array([space.target(c).conj() for c in candidates])
            self.groups.append((mask, vector, candidates, basis))

    def recall(self, context):
        identity = canonical(context)
        if identity not in self.cache:
            accepted, audits = set(), []
            for mask, vector, candidates, basis in self.groups:
                require(all(field in context for field in mask), "missing_query_field")
                key = {field: context[field] for field in mask}
                scores = np.real(basis @ (vector * self.space.key(key))) / self.space.book.dimension
                order = np.argsort(-scores, kind="stable")
                top = float(scores[order[0]])
                runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
                good = top >= .65 and top - runner >= .25
                if good:
                    accepted.add(candidates[order[0]])
                audits.append({"mask": list(mask), "value": candidates[order[0]] if good else None,
                               "score": round(top, 8), "margin": round(top-runner, 8)})
            self.cache[identity] = {"value": next(iter(accepted)) if len(accepted) == 1 else None,
                                    "reason": "recalled" if len(accepted) == 1 else "weak_or_conflicting_projection", "projections": audits}
        return json.loads(canonical(self.cache[identity]))


def fit_memory(space, observations, partial=True, enabled=True):
    leaves = dependency_leaves(observations, partial)
    require(len(leaves) <= 256, "memory_capacity_exceeded")
    masks = sorted({tuple(sorted(context)) for context, _ in leaves})
    groups = []
    for mask in masks:
        selected = [(c, t) for c, t in leaves if tuple(sorted(c)) == mask]
        vector = np.zeros(space.book.dimension, dtype=np.complex128)
        if enabled:
            for context, label in sorted(selected, key=canonical):
                vector += space.key(context).conj() * space.target(label)
        groups.append((mask, vector, sorted({t for _, t in selected})))
    stats = {"observations": len(observations), "complete_contexts": len({canonical(c) for c, _ in observations}),
             "projected_contexts": len(leaves), "masks": [list(m) for m in masks], "vectors": len(groups)}
    return ProjectionMemory(space, groups), stats
````

## `plm_l1_v04/reader.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/reader.py`  
SHA256: `682f1d0fd3c6bd9c2589e19c1760038d7049a7c413e800125399ca2e1f91246a`

````python
"""Local role recovery and learned component-consistency check, no grammar oracle."""
from .algebra import require
from .lexicon import tokenize, CONTENT, GOALS
from .features import role_context, split_gaps, status_context
from .runtime import abstain


def read(model, text):
    try:
        kinds = model.meta["kinds"]
        tokens = tokenize(text, kinds)
        meaning, positions, audit = {}, {}, []
        for i, token in enumerate(tokens):
            if kinds[token] != "marker":
                recalled = model.memories["roles"].recall(role_context(tokens, i, kinds))
                role = recalled["value"]
                require(role in CONTENT and role not in meaning, "unresolved_or_duplicate_role")
                value = model.memories["lexical_read"].recall({"surface": token})["value"]
                require(value in model.meta["slot_candidates"][role], "unresolved_lexical_value")
                meaning[role], positions[i] = value, role
                audit.append({"position": i, "role": recalled})
        order, gaps = split_gaps(tokens, positions)
        require(order[0] in GOALS and model.order(order[0]) == order, "unlearned_content_order")
        context = status_context(tokens, kinds, gaps, order)
        for slot in ("polarity", "modality"):
            recalled = model.memories[slot].recall(context)
            require(recalled["value"] in model.meta["slot_candidates"][slot], "unresolved_status")
            meaning[slot] = recalled["value"]
        # Reuse learned forward gap associations, not a hand-written language
        # rule. This rejects mismatched prefix/suffix, punctuation and markers.
        for anchor, markers in gaps.items():
            require(model.gap(meaning, order[0], anchor) == markers, "component_consistency_failed")
        return {"status": "read", "packet": model.encode(meaning), "audit": audit, "eligible_for_inference": False}
    except (ValueError, TypeError) as error:
        return abstain(str(error))
````

## `plm_l1_v04/runtime.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/runtime.py`  
SHA256: `abe8b7270932ff03ba15fb1dfa84bccdb6575250116e58115763d64a6b5b2fa7`

````python
"""Signal codec and learned component assembly; no reader/trainer imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require
from .lexicon import CONTENT, ROLES, GOALS, validate_meaning
from .features import START, gap_context
from .projection import Space, ProjectionMemory

MEMORIES = ("roles", "polarity", "modality", "order_support", "order_output", "gaps", "lexical_read", "lexical_write")


def abstain(reason, **extra):
    return {"status": "abstain", "reason": reason, "text": None, "packet": None, "eligible_for_inference": False, **extra}


class Model:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-parts-v1" and self.meta.get("eligible_for_inference") is False, "invalid_metadata")
        require(set(memories) == set(MEMORIES) and set(self.meta["slot_candidates"]) == set(ROLES), "invalid_inventory")
        self.memories = memories
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.fingerprint = digest({"metadata": self.meta, "memories": {name: [
            {"mask": list(mask), "hash": hashlib.sha256(vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(candidates)}
            for mask, vector, candidates, _ in memory.groups] for name, memory in sorted(memories.items())}})
        self.basis = {r: np.array([self.book.code("value", v).conj() for v in self.meta["slot_candidates"][r]]) for r in ROLES}

    def encode(self, meaning):
        validate_meaning(meaning, self.meta["slot_candidates"])
        vector = sum(self.book.code("semantic_role", r) * self.book.code("value", meaning[r]) for r in ROLES)
        return {"schema": "plm-l1-parts-meaning-v1", "model_fingerprint": self.fingerprint, "dimension": self.book.dimension,
                "real": vector.real.tolist(), "imag": vector.imag.tolist(), "eligible_for_inference": False}

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
            require(packet["schema"] == "plm-l1-parts-meaning-v1" and packet["model_fingerprint"] == self.fingerprint, "packet_model_mismatch")
            require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension and packet["eligible_for_inference"] is False, "invalid_contract")
            for field in ("real", "imag"):
                require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(v) in (int, float) for v in packet[field]), "invalid_signal_values")
            vector = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32., "invalid_signal")
            clean = np.zeros(self.book.dimension, dtype=np.complex128)
            meaning = {}
            for role in ROLES:
                scores = np.real(self.basis[role] @ (vector * self.book.code("semantic_role", role).conj())) / self.book.dimension
                order = np.argsort(-scores, kind="stable")
                top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
                require(top >= .65 and top-runner >= .25, "ambiguous_meaning")
                meaning[role] = self.meta["slot_candidates"][role][order[0]]
                clean += self.book.code("semantic_role", role) * self.book.code("value", meaning[role])
            residual = float(np.linalg.norm(vector-clean) / np.linalg.norm(clean))
            require(residual <= .20, "meaning_residual_excessive")
            return {"status": "recovered", "meaning": meaning, "residual": round(residual, 8), "eligible_for_inference": False}
        except (ValueError, TypeError, OverflowError) as error:
            return abstain(str(error), meaning=None)

    def order(self, goal):
        require(type(goal) is str and goal in GOALS, "unsupported_goal")
        result = self.memories["order_output"].recall({"goal": goal})
        require(result["value"] is not None, "unknown_order")
        order = json.loads(result["value"])
        require(type(order) is list and len(order) == len(CONTENT) and set(order) == set(CONTENT) and order[0] == goal, "invalid_order")
        require(self.memories["order_support"].recall({"order": order})["value"] == "supported", "unsupported_order")
        return order

    def gap(self, meaning, goal, anchor):
        recalled = self.memories["gaps"].recall(gap_context(meaning, goal, anchor))
        require(recalled["value"] is not None, "unresolved_marker_component")
        gap = json.loads(recalled["value"])
        require(type(gap) is list and len(gap) <= 9 and all(type(t) is str and self.meta["kinds"].get(t) == "marker" for t in gap), "invalid_marker_component")
        return gap

    def generate(self, packet, goal="object"):
        recovered = self.recover(packet)
        if recovered["status"] != "recovered":
            return abstain(recovered["reason"])
        meaning = recovered["meaning"]
        try:
            order = self.order(goal)
            tokens = self.gap(meaning, goal, START)
            trace = [{"anchor": START, "markers": list(tokens)}]
            for role in order:
                surface = self.memories["lexical_write"].recall({"meaning_value": meaning[role]})["value"]
                require(surface is not None and self.meta["kinds"].get(surface) in ("entity", "predicate"), "unknown_lexical_realization")
                gap = self.gap(meaning, goal, role)
                tokens += [surface] + gap
                trace.append({"anchor": role, "markers": gap})
            text = "".join(tokens)
            require(len(tokens) <= 9 and len(text) <= 256, "output_capacity_exceeded")
            return {"status": "generated", "text": text, "trace": trace, "eligible_for_inference": False}
        except ValueError as error:
            return abstain(str(error))

    def read(self, text):
        from .reader import read
        return read(self, text)

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "model.json").exists() and not (target / "weights.npz").exists(), "output_exists")
        groups, weights = {}, {}
        for name, memory in self.memories.items():
            groups[name] = []
            for i, (mask, vector, candidates, _) in enumerate(memory.groups):
                key = name + "_" + str(i)
                groups[name].append({"mask": list(mask), "candidates": list(candidates), "weight": key})
                weights[key] = vector
        info = {"metadata": self.meta, "fingerprint": self.fingerprint, "groups": groups}
        with (target / "model.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        np.savez_compressed(target / "weights.npz", **weights)

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "model.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "groups"}, "invalid_model_envelope")
        meta = info["metadata"]
        space = Space(Book(meta["dimension"], meta["seed"]))
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            expected = {g["weight"] for groups in info["groups"].values() for g in groups}
            require(expected == set(weights.files), "invalid_weight_inventory")
            memories = {name: ProjectionMemory(space, [(g["mask"], weights[g["weight"]], g["candidates"]) for g in groups]) for name, groups in info["groups"].items()}
        model = cls(meta, memories)
        require(model.fingerprint == info["fingerprint"], "model_hash_mismatch")
        return model
````

## `plm_l1_v04/training.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/plm_l1_v04/training.py`  
SHA256: `4ef26607607a4c7a8984ab4e6acf8c73f3763b947e5865959eb94a45dff6da00`

````python
"""Only text/meaning pairs and explicit initial lexicon enter this learner."""
from .algebra import Book, canonical, digest, require
from .features import observations
from .projection import Space, fit_memory
from .runtime import Model


def fit(pairs, lexicon, *, seed="parts-development-0", dimension=8192, partial=True, learning=True):
    require(type(partial) is bool and type(learning) is bool, "invalid_switches")
    rows = observations(pairs, lexicon)
    space = Space(Book(dimension, seed))
    memories, statistics = {}, {}
    for name, values in rows.items():
        memories[name], statistics[name] = fit_memory(space, values, partial, learning or name.startswith("lexical_"))
    meta = {"schema": "plm-l1-parts-v1", "seed": seed, "dimension": dimension, "partial": partial, "learning": learning,
            "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)), "lexicon_digest": digest(lexicon),
            "kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"],
            "statistics": statistics, "supervision_fields": ["text", "meaning"], "supplied_trace_supervision": False,
            "dependency_selection": "deterministic categorical information gain during training only", "eligible_for_inference": False}
    return Model(meta, memories)
````

## `prepare_data.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/prepare_data.py`  
SHA256: `2600c44d38f3dcf5294a832f90df868875efd322f90fdab6a8b99d9ab10a062d`

````python
"""Evaluator-only removal of entire construction combinations before fitting."""
import json
from plm_l1_v04.algebra import canonical, digest
from plm_l1_v04.features import observations
from evaluation_support import ROOT, FOLDS, data, text_goal, heldout


def main():
    lexicon = data("lexicon")
    audit = {"schema":"plm-l1-v04-combination-splits-v1", "folds":[], "note":"Existing v0.1-v0.3 corpus reused; new combination withholding relative to each retrained model, NOT new project-blind language data."}
    for fold in FOLDS:
        train = [r for r in data("train") if not heldout(r["meaning"],text_goal(r["text"]),fold)]
        path = ROOT / "data" / "folds" / fold / "train.json"
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("x",encoding="utf-8") as f:
            f.write(json.dumps(train,ensure_ascii=False,indent=2)+"\n")
        training_rows = observations(train,lexicon)
        pieces = {(context["anchor"],target) for context,target in training_rows["gaps"]}
        orders = {target for _,target in training_rows["order_output"]}
        counts = {}
        for split in ("development","evaluation"):
            test = [r for r in data(split) if heldout(r["meaning"],text_goal(r["text"]),fold)]
            target_rows = observations(test,lexicon)
            assert {(c["anchor"],t) for c,t in target_rows["gaps"]} <= pieces
            assert {t for _,t in target_rows["order_output"]} <= orders
            from plm_l1_v04.lexicon import tokenize
            vocabulary = {t["surface"]:t["kind"] for t in lexicon["tokens"]}
            observed = {t for r in train for t in tokenize(r["text"],vocabulary)}
            assert {t for r in test for t in tokenize(r["text"],vocabulary)} <= observed
            counts[split] = {"heldout":len(test),"seen":len(data(split))-len(test)}
        assert len(train)==432 and all(not heldout(r["meaning"],text_goal(r["text"]),fold) for r in train)
        audit["folds"].append({"fold":fold,"training_pairs":len(train),"removed_training_pairs":576-len(train),
                               "training_digest":digest(sorted(train,key=canonical)),"counts":counts,
                               "all_evaluation_marker_components_observed":True,"all_evaluation_orders_observed":True,"all_evaluation_tokens_observed":True})
    with (ROOT/"data"/"SPLIT_AUDIT.json").open("x",encoding="utf-8") as f:
        f.write(json.dumps(audit,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(audit,ensure_ascii=False))


if __name__=="__main__":
    main()
````

## `release_tools.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/release_tools.py`  
SHA256: `9773e51f22d21d82ab0d2dafa06e53073c3453f54366e30ec5e2f5ad2a062ba2`

````python
"""Additive source freezing, prior-release preservation, examples and ZIP."""
import argparse
import hashlib
import json
import zipfile
from evaluate import ROOT, source_files, verify_freeze
from evaluation_support import V03
from plm_l1_v04.algebra import digest
from plm_l1_v04.runtime import Model


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
        manifest = {"schema": "plm-l1-v04-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif command == "check-baseline":
        files = []
        for name in ("PLM-L1-v0.1", "PLM-L1-v0.2", "PLM-L1-v0.3", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        baseline = json.loads((ROOT / "verification" / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        if hashes(files, ROOT.parent) != baseline:
            raise ValueError("old release changed")
        source = ROOT.parent / "PLM-L1-v0.3"
        vendor_files = [p for p in V03.rglob("*") if p.is_file()]
        if hashes([p for p in source.rglob("*") if p.is_file()], source) != hashes(vendor_files, V03):
            raise ValueError("vendored v0.3 changed")
        print(json.dumps({"status": "unchanged", "preserved_files": len(files), "vendor_files": len(vendor_files)}))
    elif command == "demo":
        model = Model.load(ROOT / "results" / "model")
        rows = []
        for text in ("花子を太郎が助けなかった。", "もし花子を太郎が助けなかったら。", "太郎を花子が助けなかった。", "太郎が花子を助けた。", "太郎は花子を助けた。"):
            read = model.read(text)
            row = {"input": text, "read_status": read["status"], "reason": read.get("reason")}
            if read["status"] == "read":
                row["meaning"] = model.recover(read["packet"])["meaning"]
                row["generated"] = {goal: model.generate(read["packet"], goal) for goal in ("subject", "object")}
                if not rows:
                    write(ROOT / "examples" / "MEANING.json", row["meaning"])
                    write(ROOT / "examples" / "MEANING_PACKET.json", read["packet"])
            rows.append(row)
        write(ROOT / "examples" / "ROUNDTRIPS.json", {"scope": "Human/evaluator only; source text is not generator input", "training_excluded_cell": "object_negative", "demos": rows})
    else:
        verify_freeze()
        archive = ROOT.parent / "PLM-L1-v0.4.zip"
        checksum_path = ROOT.parent / "PLM-L1-v0.4.sha256"
        if archive.exists() or checksum_path.exists():
            raise ValueError("release archive already exists")
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0] != "work")
        write(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v04-release-v1", "files": hashes(files, ROOT)})
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with checksum_path.open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(files) + 1, "sha256": checksum}))


if __name__ == "__main__":
    main()
````

## `requirements.txt`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/requirements.txt`  
SHA256: `7bd6b8946940b79948c548c8048e545684b91c8edc9444d8dfc0c8f76a97c0a7`

````text
numpy==2.3.5
````

## `tests/test_parts.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/tests/test_parts.py`  
SHA256: `3ecdefa643db3c97528a4959fd3bfcb6e3cd5f735476b3ba59298b82c2f13647`

````python
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v04.algebra import Book,canonical
from plm_l1_v04.lexicon import tokenize,GOALS
from plm_l1_v04.features import observations,role_context,shape
from plm_l1_v04.projection import Space,dependency_leaves,fit_memory
from plm_l1_v04.training import fit
from plm_l1_v04.runtime import Model
from evaluation_support import data,train_for,FOLDS,heldout,text_goal,interpret,INVALID,OldSS,PartialTable,OldTable,opaque,normalize_markers
from evaluate import bad_packets


class PartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex=data("lexicon")
        cls.models={fold:fit(train_for(fold),cls.lex) for fold in FOLDS}
        cls.model=cls.models[FOLDS[0]]
        cls.text="花子を太郎が助けなかった。"
        cls.meaning=interpret(cls.text)
        cls.packet=cls.model.encode(cls.meaning)

    def test_all_folds_development_reading(self):
        for fold,model in self.models.items():
            for row in data("development"):
                with self.subTest(fold=fold,text=row["text"]):
                    r=model.read(row["text"])
                    self.assertEqual(r["status"],"read")
                    self.assertEqual(model.recover(r["packet"])["meaning"],row["meaning"])

    def test_all_folds_development_generation(self):
        for model in self.models.values():
            for row in data("development"):
                for goal in GOALS:
                    out=model.generate(model.encode(row["meaning"]),goal)
                    self.assertEqual(interpret(out["text"]),row["meaning"])
                    self.assertEqual(text_goal(out["text"]),goal)

    def test_novel_roundtrip_all_folds(self):
        for fold,model in self.models.items():
            for row in data("development"):
                goal=text_goal(row["text"])
                if heldout(row["meaning"],goal,fold):
                    out=model.generate(model.read(row["text"])["packet"],goal)
                    self.assertEqual(out["text"],row["text"])

    def test_entire_cell_excluded(self):
        for fold in FOLDS:
            train=train_for(fold)
            self.assertEqual(len(train),432)
            self.assertFalse(any(heldout(r["meaning"],text_goal(r["text"]),fold) for r in train))
            self.assertEqual(sum(heldout(r["meaning"],text_goal(r["text"]),fold) for r in data("evaluation")),48)

    def test_components_and_tokens_are_known(self):
        kinds={t["surface"]:t["kind"] for t in self.lex["tokens"]}
        for fold in FOLDS:
            train=train_for(fold)
            test=[r for r in data("evaluation") if heldout(r["meaning"],text_goal(r["text"]),fold)]
            a,b=observations(train,self.lex),observations(test,self.lex)
            self.assertLessEqual({(c["anchor"],t) for c,t in b["gaps"]},{(c["anchor"],t) for c,t in a["gaps"]})
            self.assertLessEqual({t for r in test for t in tokenize(r["text"],kinds)},{t for r in train for t in tokenize(r["text"],kinds)})

    def test_lexical_composition_split_stays_disjoint(self):
        keys=lambda rows:{tuple(r["meaning"][s] for s in ("subject","object","predicate")) for r in rows}
        a,b,c=[keys(data(s)) for s in ("train","development","evaluation")]
        self.assertFalse(a&b or a&c or b&c)

    def test_old_ss_matched_training_control(self):
        old=OldSS(train_for(FOLDS[0]),self.lex,"parts-development-0")
        self.assertEqual(old.meta["pair_count"],432)
        self.assertEqual(old.read(self.text)["status"],"abstain")
        self.assertEqual(old.generate(old.encode(self.meaning),"object")["status"],"abstain")
        known="太郎が花子を助けなかった。"
        self.assertEqual(old.read(known)["status"],"read")
        self.assertEqual(old.generate(old.encode(self.meaning),"subject")["text"],known)

    def test_full_context_control_preserves_seen(self):
        full=fit(train_for(FOLDS[0]),self.lex,partial=False)
        for row in data("development"):
            goal=text_goal(row["text"])
            is_novel=heldout(row["meaning"],goal,FOLDS[0])
            self.assertEqual(full.read(row["text"])["status"],"abstain" if is_novel else "read")
            self.assertEqual(full.generate(full.encode(row["meaning"]),goal)["status"],"abstain" if is_novel else "generated")

    def test_no_learning_keeps_lexical_prior(self):
        model=fit(train_for(FOLDS[0]),self.lex,learning=False)
        self.assertEqual(model.memories["lexical_read"].recall({"surface":"太郎"})["value"],"entity:太郎")
        self.assertEqual(model.read(self.text)["status"],"abstain")
        self.assertEqual(model.generate(model.encode(self.meaning))["status"],"abstain")

    def test_partial_table_is_successful_too(self):
        model=PartialTable(train_for(FOLDS[0]),self.lex)
        self.assertEqual(model.read(self.text)["status"],"read")
        self.assertEqual(model.generate(model.encode(self.meaning))["text"],self.text)

    def test_old_table_cannot_reuse(self):
        model=OldTable(train_for(FOLDS[0]),self.lex)
        self.assertEqual(model.read(self.text)["status"],"abstain")
        self.assertEqual(model.generate(model.encode(self.meaning))["status"],"abstain")

    def test_typed_feature_bindings_do_not_alias(self):
        space=Space(Book())
        self.assertGreater(np.linalg.norm(space.key({"goal":"subject","anchor":"object"})-space.key({"goal":"object","anchor":"subject"})),1.)

    def test_sequence_order_preserved(self):
        space=Space(Book())
        self.assertGreater(np.linalg.norm(space.target(canonical(["subject","object"]))-space.target(canonical(["object","subject"]))),1.)

    def test_dependencies_are_learned_not_supplied(self):
        for model in self.models.values():
            stats=model.meta["statistics"]
            self.assertNotIn("whole_shape",{f for m in stats["roles"]["masks"] for f in m})
            self.assertNotIn("goal",{f for m in stats["gaps"]["masks"] for f in m})
            self.assertEqual(stats["modality"]["masks"],[["leading_markers"]])
        self.assertEqual(list(inspect.signature(fit).parameters),["pairs","lexicon","seed","dimension","partial","learning"])

    def test_dependency_can_retain_goal_when_data_requires_it(self):
        pairs=copy.deepcopy(data("train"))
        for row in pairs:
            if text_goal(row["text"])=="object":
                p=row["meaning"]["polarity"]
                row["meaning"]["polarity"]="polarity:positive" if p=="polarity:negative" else "polarity:negative"
        model=fit(pairs,self.lex)
        self.assertIn("goal",{f for mask in model.meta["statistics"]["gaps"]["masks"] for f in mask})
        out=model.generate(model.encode(interpret("太郎が花子を助けた。")),"object")
        self.assertEqual(out["text"],"花子を太郎が助けなかった。")

    def test_projection_selector_independent_example(self):
        obs=[({"relevant":r,"nuisance":n},r) for r in ("a","b") for n in ("x","y")]
        leaves=dependency_leaves(obs)
        self.assertTrue(all(set(c)=={"relevant"} for c,_ in leaves))
        memory,_=fit_memory(Space(Book()),obs)
        self.assertEqual(memory.recall({"relevant":"a","nuisance":"never_seen"})["value"],"a")

    def test_positive_only_support_not_universal(self):
        obs=[({"x":"known"},"supported")]
        self.assertEqual(dependency_leaves(obs),obs)
        memory,_=fit_memory(Space(Book()),obs)
        self.assertIsNone(memory.recall({"x":"unknown"})["value"])

    def test_no_runtime_tree_or_leaf_table(self):
        for mem in self.model.memories.values():
            self.assertFalse(hasattr(mem,"leaves") or hasattr(mem,"tree"))
        serialized=canonical(self.model.meta)
        self.assertTrue(all(row["text"] not in serialized for row in train_for(FOLDS[0])))

    def test_pair_only_api(self):
        for field in ("goal","order","fold","heldout","actions","states","trace","roles"):
            with self.assertRaises(ValueError):
                fit([dict(train_for(FOLDS[0])[0],**{field:[]})],self.lex)

    def test_opaque_markers(self):
        pairs,lex,mapping=opaque(train_for(FOLDS[0]),self.lex)
        model=fit(pairs,lex)
        text=normalize_markers(self.text,mapping)
        self.assertEqual(model.recover(model.read(text)["packet"])["meaning"],self.meaning)
        self.assertEqual(model.generate(model.encode(self.meaning))["text"],text)

    def test_counterfactual_role_labels(self):
        pairs=copy.deepcopy(train_for(FOLDS[0]))
        for row in pairs:
            m=row["meaning"]
            m["subject"],m["object"]=m["object"],m["subject"]
        model=fit(pairs,self.lex)
        expected=dict(self.meaning,subject=self.meaning["object"],object=self.meaning["subject"])
        self.assertEqual(model.recover(model.read(self.text)["packet"])["meaning"],expected)

    def test_ambiguous_alignment_rejected(self):
        text="太郎が太郎を助けた。"
        with self.assertRaises(ValueError):
            fit([{"text":text,"meaning":interpret(text)}],self.lex)

    def test_conflicting_labels_rejected(self):
        rows=copy.deepcopy(train_for(FOLDS[0])[:1])
        other=copy.deepcopy(rows[0])
        other["meaning"]["subject"],other["meaning"]["object"]=other["meaning"]["object"],other["meaning"]["subject"]
        with self.assertRaises(ValueError):
            fit(rows+[other],self.lex)

    def test_marker_semantics_prohibited(self):
        lex=copy.deepcopy(self.lex)
        next(t for t in lex["tokens"] if t["kind"]=="marker")["value"]="negative"
        with self.assertRaises(ValueError):
            fit(train_for(FOLDS[0]),lex)

    def test_invalid_texts_all_folds(self):
        for model in self.models.values():
            for text in INVALID:
                self.assertEqual(model.read(text)["status"],"abstain")

    def test_mismatched_parts_rejected(self):
        for text in ("もし太郎が花子を助けた。","太郎が花子を助けたら。","花子が太郎が助けなかった。","花子を太郎が助けなかった。。"):
            self.assertEqual(self.model.read(text)["status"],"abstain")

    def test_unlearned_role_order_rejected(self):
        self.assertEqual(self.model.read("助けた。花子を太郎が")["status"],"abstain")

    def test_unknown_vocabulary_rejected(self):
        self.assertEqual(self.model.read("未知が花子を助けた。")["status"],"abstain")
        with self.assertRaises(ValueError):
            self.model.encode(dict(self.meaning,subject="entity:未知"))

    def test_missing_parts_not_reconstructed_from_gold(self):
        self.assertEqual(self.model.read("花子を助けなかった。")["status"],"abstain")

    def test_self_reference_inference(self):
        text="太郎が太郎を助けなかった。"
        result=self.model.read(text)
        self.assertEqual(self.model.recover(result["packet"])["meaning"],interpret(text))

    def test_signal_only_packet(self):
        self.assertEqual(set(self.packet),{"schema","model_fingerprint","dimension","real","imag","eligible_for_inference"})
        self.assertNotIn("太郎",canonical(self.packet))

    def test_invalid_packets(self):
        for p in bad_packets(self.model,self.meaning):
            self.assertEqual(self.model.generate(p)["status"],"abstain")

    def test_extra_packet_fields(self):
        for field in ("gold","trace","source","order","parts"):
            self.assertEqual(self.model.generate(dict(self.packet,**{field:[]}))["status"],"abstain")

    def test_nonobject_packets_and_text(self):
        for value in (None,[],1,True):
            self.assertEqual(self.model.generate(value)["status"],"abstain")
            self.assertEqual(self.model.read(value)["status"],"abstain")

    def test_unknown_goal(self):
        for goal in (None,"essay",[]):
            self.assertEqual(self.model.generate(self.packet,goal)["status"],"abstain")

    def test_inference_disabled(self):
        for output in (self.packet,self.model.read(self.text),self.model.generate(self.packet),self.model.recover(self.packet)):
            self.assertFalse(output["eligible_for_inference"])

    def test_generator_never_calls_reader(self):
        with patch.object(Model,"read",side_effect=AssertionError("reader forbidden")):
            self.assertEqual(self.model.generate(self.packet)["text"],self.text)

    def test_no_old_teacher_or_model_calls(self):
        import plm_l1.teacher as teacher
        from plm_l1_v03.runtime import Writer
        from plm_l1_v02.runtime import PairReader
        with patch.object(teacher,"reader_trace",side_effect=AssertionError()),patch.object(teacher,"writer_trace",side_effect=AssertionError()),patch.object(Writer,"generate",side_effect=AssertionError()),patch.object(PairReader,"read",side_effect=AssertionError()):
            model=fit(train_for(FOLDS[0]),self.lex)
            self.assertEqual(model.generate(model.read(self.text)["packet"])["text"],self.text)

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            model=Model.load(directory)
            self.assertEqual(model.fingerprint,self.model.fingerprint)
            self.assertEqual(model.generate(self.packet),self.model.generate(self.packet))

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            with self.assertRaises(ValueError):
                self.model.save(directory)

    def test_metadata_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            p=Path(directory)/"model.json"
            info=json.loads(p.read_text(encoding="utf-8"))
            info["metadata"]["pair_count"]+=1
            p.write_text(json.dumps(info),encoding="utf-8")
            with self.assertRaises(ValueError):
                Model.load(directory)

    def test_weight_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            p=Path(directory)/"weights.npz"
            with np.load(p,allow_pickle=False) as a:
                values={k:a[k] for k in a.files}
            next(iter(values.values()))[0]+=1
            np.savez_compressed(p,**values)
            with self.assertRaises(ValueError):
                Model.load(directory)

    def test_deterministic_pair_order(self):
        model=fit(list(reversed(train_for(FOLDS[0]))),self.lex)
        self.assertEqual(model.fingerprint,self.model.fingerprint)

    def test_duplicate_examples_do_not_inflate_weights(self):
        model=fit(train_for(FOLDS[0])*2,self.lex)
        for name in model.memories:
            for a,b in zip(model.memories[name].groups,self.model.memories[name].groups):
                np.testing.assert_array_equal(a[1],b[1])

    def test_invalid_fit_settings(self):
        for kwargs in ({"partial":1},{"learning":0},{"dimension":129},{"seed":""}):
            with self.assertRaises(ValueError):
                fit(train_for(FOLDS[0]),self.lex,**kwargs)

    def test_no_hidden_japanese_grammar(self):
        from plm_l1_v04 import training,reader,runtime,features,projection
        for module in (training,reader,runtime,features,projection):
            code=inspect.getsource(module)
            for text in ("太郎","花子","もし","なかった",'"が"','"を"',"from evaluation_support","import plm_l1_v03","import plm_l1_v02"):
                self.assertNotIn(text,code)


if __name__=="__main__":
    unittest.main()
````

## `verify_release.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/vendor/PLM-L1-v0.5/vendor/PLM-L1-v0.4/verify_release.py`  
SHA256: `b2b34ca0739bf1680eb9456b94e2752f2383cdd3fc4ab7b2b9d2921c165fcba8`

````python
"""Test suites, fixed-result integrity and physically isolated learning/generation."""
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
from evaluation_support import ROOT, V03, V02, train_for, data, interpret, text_goal
from plm_l1_v04.algebra import digest
from plm_l1_v04.runtime import Model


def run(arguments, cwd, output, label, expected=0):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH", None)
    completed = subprocess.run([sys.executable, "-B", *arguments], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    log = completed.stdout + completed.stderr
    (output / (label + ".log")).write_text(log, encoding="utf-8")
    if completed.returncode != expected:
        raise ValueError(label + " failed: " + log[-2000:])
    return completed.stdout, log


def copy_package(source, target, excluded=()):
    target.mkdir(parents=True)
    for path in sorted(source.glob("*.py")):
        if path.name not in excluded:
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
    protocol = json.loads((ROOT / "evaluation" / "PROTOCOL.json").read_text(encoding="utf-8"))
    if args.preflight:
        from plm_l1_v04.training import fit
        model = fit(train_for(protocol["folds"][0]), data("lexicon"), seed=protocol["development_seeds"][0])
        freeze, claimed, checks = "preflight_not_frozen", None, []
    else:
        freeze = verify_freeze()
        result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
        claimed = result.pop("result_digest")
        if digest(result) != claimed or result["freeze_hash"] != freeze:
            raise ValueError("evaluation integrity failure")
        checks = judge(result["results"], protocol, result["regressions"])
        if checks != result["checks"] or len(checks) != 209 or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        model = Model.load(ROOT / "results" / "model")
        first = result["results"][0]
        if first["condition"] != "partial" or first["fingerprint"] != model.fingerprint:
            raise ValueError("saved model differs from evaluation")
    test_counts = {}
    for label, cwd in (("NEW_TESTS", ROOT), ("V03_TESTS", V03), ("V02_TESTS", V02), ("V01_TESTS", V02 / "vendor" / "PLM-L1-v0.1")):
        _, log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], cwd, output, label)
        test_counts[label] = int(re.search(r"Ran (\d+) tests", log).group(1))

    # Same 432 training pairs and initial lexicon, no old packages or evaluators.
    training_only = output / "pair-training-only"
    copy_package(ROOT / "plm_l1_v04", training_only / "plm_l1_v04")
    shutil.copyfile(ROOT / "data" / "folds" / protocol["folds"][0] / "train.json", training_only / "train.json")
    shutil.copyfile(ROOT / "data" / "lexicon.json", training_only / "lexicon.json")
    assertion = "from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert all(importlib.util.find_spec(n) is None for n in ('plm_l1','plm_l1_v02','plm_l1_v03','evaluation_support')); assert not Path('evaluation.json').exists(); print('pair learner: no legacy model, teacher or evaluation corpus')"
    run(["-c", assertion], training_only, output, "PAIR_TRAIN_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v04", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", model.meta["seed"], "--dimension", str(model.meta["dimension"]), "--out", "model"], training_only, output, "PAIR_TRAIN")
    if json.loads(stdout)["fingerprint"] != model.fingerprint:
        raise ValueError("isolated training differs")

    # Generation executable has neither reader.py nor training.py. Shared
    # numerical memories and feature/codec helpers remain: this is not proof
    # of absent reader-related knowledge or of all-symbolic-code removal.
    generation_only = output / "generation-only"
    copy_package(ROOT / "plm_l1_v04", generation_only / "plm_l1_v04", {"reader.py", "training.py"})
    shutil.copytree(training_only / "model", generation_only / "model")
    assertion = "from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('plm_l1_v04.reader','plm_l1_v04.training','plm_l1_v03','plm_l1_v02','plm_l1','evaluation_support')); assert not Path('train.json').exists(); print('generation: no reader/training entrypoint, legacy package or corpus; shared weights remain')"
    run(["-c", assertion], generation_only, output, "GENERATION_BOUNDARY")
    demos = []
    texts = ("花子を太郎が助けなかった。", "もし花子を太郎が助けなかったら。", "太郎を花子が助けなかった。", "太郎が花子を助けた。")
    for i, text in enumerate(texts):
        packet_name = f"meaning-{i}.json"
        run(["-m", "plm_l1_v04", "read", "--model", "model", "--text", text, "--out", packet_name], training_only, output, f"READ_{i}")
        packet = json.loads((training_only / packet_name).read_text(encoding="utf-8"))
        if set(packet) != {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}:
            raise ValueError("non-numerical payload leaked")
        shutil.copyfile(training_only / packet_name, generation_only / packet_name)
        stdout, _ = run(["-m", "plm_l1_v04", "generate", "--model", "model", "--packet", packet_name, "--goal", "object"], generation_only, output, f"GENERATE_{i}")
        out = json.loads(stdout)
        if out["status"] != "generated" or interpret(out["text"]) != interpret(text) or text_goal(out["text"]) != "object":
            raise ValueError("isolated generation changed meaning or goal")
        demos.append({"input_for_verifier_only": text, "output": out["text"], "meaning_and_goal_exact": True})
    # No feature selection/tree induction is invoked during inference.
    assertion = "import json; from unittest.mock import patch; from plm_l1_v04.runtime import Model; m=Model.load('model'); p=json.load(open('meaning-0.json',encoding='utf-8')); guard=patch('plm_l1_v04.projection.dependency_leaves',side_effect=AssertionError('runtime retraining')); guard.start(); assert m.generate(p,'object')['status']=='generated'; print('no runtime dependency learner call')"
    run(["-c", assertion], generation_only, output, "NO_RUNTIME_FEATURE_LEARNING")
    run(["-m", "plm_l1_v04", "read", "--model", "model", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], training_only, output, "ABSTAIN", expected=2)
    if (training_only / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")

    manifest_checked = False
    manifest_path = ROOT / "RELEASE_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual_files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p != manifest_path and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0] != "work"}
        if actual_files != set(manifest["files"]):
            raise ValueError("release inventory changed")
        for name, expected in manifest["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("release file changed: " + name)
        manifest_checked = True
    report = {"status": "passed", "preflight": args.preflight, "source_freeze": freeze,
              "result_digest": claimed, "acceptance_checks": len(checks), "test_counts": test_counts,
              "pair_training_without_legacy_teacher_or_evaluation_data": True,
              "isolated_model_fingerprint_equal": True, "model_fingerprint": model.fingerprint,
              "generation_without_reader_or_training_entrypoint_or_corpora": True,
              "numerical_packet_only_transfer": True, "no_runtime_feature_learning": True,
              "boundary_limit": "Shared full numerical model and feature helpers remain in generation-only environment.",
              "isolated_roundtrips": demos, "release_manifest_checked": manifest_checked,
              "full_numeric_rerun_in_this_command": False, "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

