# PLM-L1-v0.6 全コード（当該版直下・vendor重複除外）

原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。

## `evaluate.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/evaluate.py`  
SHA256: `c092bc3e8607e4a3ac6983608d25b95ab243fae68f26767e48ae7ec3d9a1d443`

````python
"""Frozen matched-subsystem comparisons and independent language scoring."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from plm_l1_v06.algebra import digest
from plm_l1_v06.training import fit
from evaluation_support import ROOT, data, train_for
from measurements import BUCKETS, assess, empty_counts, count
from memory_bench import measure


def source_files():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py",".md",".txt")]
    for name in ("plm_l1_v06","tests","evaluation","data","vendor"):
        files += [p for p in (ROOT/name).rglob("*") if p.is_file()]
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix!=".pyc")


def verify_freeze():
    manifest=json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    if actual!=manifest["files"]:
        raise ValueError("frozen source changed")
    return digest(manifest)


def judge(result,protocol):
    checks=[]
    def add(name,passed,**context):
        checks.append({"name":name,"passed":bool(passed),**context})
    expected={(f,s) for f in protocol["folds"] for s in protocol["evaluation_seeds"]}
    if len(result["standard"])!=len(expected) or {(r["fold"],r["seed"]) for r in result["standard"]}!=expected:
        raise ValueError("standard inventory differs")
    for r in result["standard"]:
        if set(r["methods"])!=set(protocol["standard_modes"]) or any(v["training_pairs"]!=432 for v in r["methods"].values()):
            raise ValueError("standard methods/training budget differ")
        if r["dimension"]!=protocol["dimension"]:
            raise ValueError("standard dimension differs")
        for method in r["methods"].values():
            recounted=empty_counts(BUCKETS)
            for row in method["records"]:
                count(recounted,row["bucket"],row["status"] in ("read","generated"),row["exact"])
            if any(method["counts"][k]!=v for k,v in recounted.items()):
                raise ValueError("language counts differ from records")
        a,b=r["methods"]["split_proof"]["counts"],r["methods"]["single"]["counts"]
        ctx={"fold":r["fold"],"seed":r["seed"]}
        for key in BUCKETS:
            add(key+"_coverage",a[key+"_exact"]/a[key+"_requests"]>=.98,**ctx)
            add(key+"_preserved",a[key+"_exact"]==b[key+"_exact"] and a[key+"_requests"]==b[key+"_requests"],**ctx)
        add("standard_safety",all(a[k+"_wrong"]==0 for k in BUCKETS) and a["invalid_text_accepted"]+a["invalid_packet_generated"]+a["read_signal_unrecoverable"]==0,**ctx)
        stores=r["storage"]
        add("language_subsystem_budget_equal",len({sum(v["owned_heap_bytes"] for v in x.values()) for x in stores.values()})==1,**ctx)
        add("language_splitting_active",any(b>1 for st in r["bank_statistics"].values() for b in st["bank_counts"]),**ctx)
    expected={(s,d,n,"ordinary") for s in protocol["memory_seeds"] for d in protocol["memory_dimensions"] for n in protocol["memory_loads"]}
    expected|={(s,protocol["skew_dimension"],protocol["skew_load"],"forced_single_bank") for s in protocol["memory_seeds"]}
    if len(result["memory"])!=len(expected) or {(r["seed"],r["dimension"],r["load"],r["scenario"]) for r in result["memory"]}!=expected:
        raise ValueError("memory inventory differs")
    for r in result["memory"]:
        methods=r["methods"]
        if set(methods)!=set(protocol["all_modes"]):
            raise ValueError("memory modes differ")
        for method in methods.values():
            recounted=empty_counts(("known","missing"))
            for row in method["records"]:
                known=row["expected"] is not None
                accepted=row["recalled"] is not None
                count(recounted,"known" if known else "missing",accepted,accepted and known and row["recalled"]==row["expected"])
            if any(method["counts"][k]!=v for k,v in recounted.items()) or recounted["known_requests"]!=r["load"] or recounted["missing_requests"]!=protocol["missing_queries"]:
                raise ValueError("memory counts differ from records")
        ctx={k:r[k] for k in ("seed","dimension","load","scenario")}
        sizes=[m["statistics"] for m in methods.values()]
        add("fixed_memory_budget",all(len({s[k] for s in sizes})==1 for k in ("owned_heap_bytes","state_bytes","numerical_weight_bytes","cache_capacity_bytes")),**ctx)
        a,b=methods["split_proof"]["records"],methods["split_unchecked"]["records"]
        add("single_block_evidence_only_removes",methods["split_proof"]["weight_digest"]==methods["split_unchecked"]["weight_digest"] and len(a)==len(b)==r["load"]+protocol["missing_queries"] and all(x["recalled"] is None or x["recalled"]==y["recalled"] for x,y in zip(a,b)),**ctx)
        add("ordinary_dictionary_control",r["table_reference"]["known_exact"]==r["load"] and r["table_reference"]["missing_correct_rejection"]==protocol["missing_queries"],**ctx)
        if r["scenario"]=="ordinary" and r["dimension"]==8192 and r["load"]<=32:
            add("low_load_memory_coverage",methods["split_proof"]["counts"]["known_exact"]/r["load"]>=.98,**ctx)
    totals={m:{k:sum(r["methods"][m]["counts"][k] for r in result["memory"] if r["scenario"]=="ordinary") for k in ("known_exact","known_wrong","missing_accepted")} for m in protocol["all_modes"]}
    a,b=totals["split_proof"],totals["single"]
    add("aggregate_missing_suppression",a["missing_accepted"]<b["missing_accepted"])
    add("aggregate_wrong_suppression",a["known_wrong"]<b["known_wrong"])
    add("aggregate_correct_retention_guard",a["known_exact"]>=.5*b["known_exact"])
    add("no_learning_not_success",all(result["no_learning"]["counts"][k+"_accepted"]==0 for k in BUCKETS))
    full=result["full_training"]["counts"]
    add("full_training_regression",all(full[k+"_exact"]==full[k+"_requests"] for k in BUCKETS) and full["invalid_text_accepted"]+full["invalid_packet_generated"]+full["read_signal_unrecoverable"]==0)
    return checks


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
    standard,telemetry=[],[]
    for fold in protocol["folds"]:
        for seed in seeds:
            r={"fold":fold,"seed":seed,"dimension":protocol["dimension"],"methods":{},"storage":{}}
            for mode in protocol["standard_modes"]:
                start=time.perf_counter()
                model=fit(train_for(fold),data("lexicon"),seed=seed,dimension=protocol["dimension"],memory_mode=mode)
                r["methods"][mode]=assess(model,split,fold)
                r["storage"][mode]={n:m.storage() for n,m in model.memories.items()}
                if mode=="split_proof":
                    r["bank_statistics"]=model.meta["statistics"]
                    if not standard:
                        model.save(output/"model")
                telemetry.append({"section":"standard","fold":fold,"seed":seed,"mode":mode,"elapsed_seconds":time.perf_counter()-start})
            standard.append(r)
            print(json.dumps({"standard":fold,"seed":seed,"read_heldout_exact":r["methods"]["split_proof"]["counts"]["read_heldout_exact"]}),flush=True)
    memory=[]
    memory_seeds=protocol["development_seeds"] if args.development else protocol["memory_seeds"]
    for seed in memory_seeds:
        settings=[(d,n,"ordinary") for d in protocol["memory_dimensions"] for n in protocol["memory_loads"]]
        settings.append((protocol["skew_dimension"],protocol["skew_load"],"forced_single_bank"))
        for d,n,scenario in settings:
            r,t=measure(d,n,seed,protocol["all_modes"],protocol["missing_queries"],scenario)
            memory.append(r)
            telemetry.append({"section":"memory","dimension":d,"load":n,"seed":seed,"scenario":scenario,"measurements":t})
            print(json.dumps({"memory":scenario,"dimension":d,"load":n,"seed":seed}),flush=True)
    full=assess(fit(data("train"),data("lexicon"),seed="banked-full-regression-0"),split,protocol["folds"][0])
    no_learning=assess(fit(train_for(protocol["folds"][0]),data("lexicon"),learning=False),split,protocol["folds"][0])
    result={"schema":"plm-l1-v06-results-v1","freeze_hash":freeze,"standard":standard,"memory":memory,"full_training":full,"no_learning":no_learning}
    result["checks"]=[] if args.development else judge(result,protocol)
    result["passed"]=bool(result["checks"]) and all(c["passed"] for c in result["checks"])
    result["result_digest"]=digest(result)
    (output/"EVALUATION.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (output/"TELEMETRY.json").write_text(json.dumps(telemetry,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    from report import write_report
    write_report(output,result)
    print("RESULT_DIGEST "+result["result_digest"],flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
````

## `evaluation_support.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/evaluation_support.py`  
SHA256: `0ec820ba11c7a5e323bfb93d306cbbe8c13609adb0b49fb69766514529938788`

````python
"""Evaluation-only legacy controls and independent language scorer."""
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent
V05 = ROOT / "vendor" / "PLM-L1-v0.5"
V04 = V05 / "vendor" / "PLM-L1-v0.4"
V03 = V04 / "vendor" / "PLM-L1-v0.3"
V02 = V03 / "vendor" / "PLM-L1-v0.2"
V01 = V02 / "vendor" / "PLM-L1-v0.1"
for path in (V05, V04, V03, V02, V01):
    if str(path) not in sys.path:
        sys.path.append(str(path))
spec = importlib.util.spec_from_file_location("legacy_v04_evaluation_support", V04 / "evaluation_support.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
FOLDS, GOALS = legacy.FOLDS, legacy.GOALS
heldout, text_goal, interpret, INVALID = legacy.heldout, legacy.text_goal, legacy.interpret, legacy.INVALID
OldSS, PartialTable, OldTable = legacy.OldSS, legacy.PartialTable, legacy.OldTable
opaque, normalize_markers = legacy.opaque, legacy.normalize_markers


def data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def train_for(fold):
    return data("folds/" + fold + "/train")
````

## `measurements.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/measurements.py`  
SHA256: `7dff7847d3b2d2bb021664e44736b851fd7aecde91e38538c35f9003234f8009`

````python
"""Independent scoring and explicitly separated numerical stress experiments."""
import copy
import hashlib
import json
import numpy as np
from plm_l1_v06.algebra import Book, canonical, require
from plm_l1_v06.projection import Space, fit_memory
from evaluation_support import data, heldout, text_goal, interpret, INVALID, GOALS

BUCKETS = ("read_heldout", "read_seen", "generate_heldout", "generate_seen", "roundtrip_both_heldout", "roundtrip_other")


def bad_packets(model, meaning):
    p = model.encode(meaning)
    n = p["dimension"]
    result = [dict(p,text="hidden source"), dict(p,meaning=meaning), dict(p,model_fingerprint="bad"), dict(p,dimension=0),
              dict(p,eligible_for_inference=True), dict(p,real=[0.]*n,imag=[0.]*n)]
    for value in (float("nan"),float("inf"),True,"1",1e100):
        q = copy.deepcopy(p)
        q["real"][0] = value
        result.append(q)
    result.append(dict(p,real=p["real"][:-1]))
    return result


def vector_digest(packet):
    v = np.array(packet["real"]) + 1j*np.array(packet["imag"])
    return hashlib.sha256(v.astype("<c16").tobytes()).hexdigest()


def empty_counts(prefixes):
    return {p+"_"+k:0 for p in prefixes for k in ("requests","exact","accepted","wrong","abstained")}


def count(c,prefix,accepted,exact):
    c[prefix+"_requests"] += 1
    c[prefix+"_accepted"] += int(accepted)
    c[prefix+"_exact"] += int(exact)
    c[prefix+"_wrong"] += int(accepted and not exact)
    c[prefix+"_abstained"] += int(not accepted)


def assess(model, split, fold):
    rows = data(split)
    c, records = empty_counts(BUCKETS), []
    c.update(read_signal_unrecoverable=0, read_recoverable_but_semantically_wrong=0)
    meanings = {canonical(r["meaning"]):r["meaning"] for r in rows}
    for key in sorted(meanings):
        meaning = meanings[key]
        packet = model.encode(meaning)
        for goal in GOALS:
            out = model.generate(packet,goal)
            prefix = "generate_" + ("heldout" if heldout(meaning,goal,fold) else "seen")
            accepted = out["status"] == "generated"
            exact = accepted and interpret(out["text"]) == meaning and text_goal(out["text"]) == goal
            count(c,prefix,accepted,exact)
            records.append({"stage":"generate","bucket":prefix,"expected":meaning,"goal":goal,"status":out["status"],"output":out.get("text"),"exact":exact,"reason":out.get("reason")})
    for row in rows:
        read = model.read(row["text"])
        accepted = read["status"] == "read"
        recovered = model.recover(read["packet"]) if accepted else {"status":"not_requested","meaning":None}
        recoverable = recovered["status"] == "recovered"
        exact = recoverable and recovered["meaning"] == row["meaning"]
        novel = heldout(row["meaning"],text_goal(row["text"]),fold)
        prefix = "read_" + ("heldout" if novel else "seen")
        count(c,prefix,accepted,exact)
        c["read_signal_unrecoverable"] += int(accepted and not recoverable)
        c["read_recoverable_but_semantically_wrong"] += int(recoverable and not exact)
        records.append({"stage":"read","bucket":prefix,"input":row["text"],"expected":row["meaning"],"status":read["status"],"recovered":recovered.get("meaning"),"exact":exact,
                        "reason":read.get("reason"),"recovery_reason":read.get("recovery_reason",recovered.get("reason")),"signal_verified":read.get("signal_verified",False),
                        "signal_digest":vector_digest(read["packet"]) if accepted else None})
        for goal in GOALS:
            out = model.generate(read["packet"],goal) if accepted else {"status":"abstain","reason":"reader_abstained"}
            prefix = "roundtrip_" + ("both_heldout" if novel and heldout(row["meaning"],goal,fold) else "other")
            generated = out["status"] == "generated"
            exact = generated and interpret(out["text"]) == row["meaning"] and text_goal(out["text"]) == goal
            count(c,prefix,generated,exact)
            records.append({"stage":"roundtrip","bucket":prefix,"input_for_evaluator_only":row["text"],"expected":row["meaning"],"goal":goal,"output":out.get("text"),"status":out["status"],"reason":out.get("reason"),"exact":exact})
    invalid = [{"input":t,"status":model.read(t)["status"]} for t in INVALID]
    bad = [{"index":i,"status":model.generate(p)["status"]} for i,p in enumerate(bad_packets(model,next(iter(meanings.values()))))]
    c.update(invalid_text_requests=len(invalid),invalid_text_accepted=sum(r["status"]=="read" for r in invalid),invalid_packet_requests=len(bad),invalid_packet_generated=sum(r["status"]=="generated" for r in bad))
    return {"counts":c,"records":records,"invalid_texts":invalid,"invalid_packets":bad,"fingerprint":model.fingerprint,"training_pairs":model.meta["pair_count"]}


def accepted_subset(new,old):
    """New acceptance never invents a signal or completed output absent before."""
    for a,b in zip(new["records"],old["records"]):
        if a["status"] in ("read","generated"):
            field = "signal_digest" if a["stage"] == "read" else "output"
            if b["status"] != a["status"] or b[field] != a[field]:
                return False
    return len(new["records"]) == len(old["records"])


def noisy_packet(packet,relative_l2,seed,identity):
    """Post-reader perturbation; no trusted 'already verified' bypass flag."""
    require(type(relative_l2) in (int,float) and np.isfinite(relative_l2) and relative_l2>=0,"invalid_noise")
    p = copy.deepcopy(packet)
    if relative_l2 == 0:
        return p
    v = np.array(p["real"]) + 1j*np.array(p["imag"])
    key = int.from_bytes(hashlib.sha256(canonical([seed,identity]).encode("utf-8")).digest()[:16],"little")
    rng = np.random.Generator(np.random.PCG64(key))
    z = rng.standard_normal(len(v)) + 1j*rng.standard_normal(len(v))
    z *= relative_l2*np.linalg.norm(v)/np.linalg.norm(z)
    v += z
    p["real"],p["imag"] = v.real.tolist(),v.imag.tolist()
    return p


def channel(model,split,level,noise_seed):
    c,records = empty_counts(("source_read","recover","generate")),[]
    for row in data(split):
        read = model.read(row["text"])
        accepted = read["status"] == "read"
        clean = model.recover(read["packet"]) if accepted else {"meaning":None}
        count(c,"source_read",accepted,accepted and clean.get("meaning")==row["meaning"])
        if not accepted:
            records.append({"input_for_evaluator_only":row["text"],"source_status":"abstain","source_reason":read.get("reason")})
            continue
        p = noisy_packet(read["packet"],level,noise_seed,row["text"])
        recovered = model.recover(p)
        exact = recovered["status"]=="recovered" and recovered["meaning"]==row["meaning"]
        count(c,"recover",recovered["status"]=="recovered",exact)
        outputs=[]
        for goal in GOALS:
            out = model.generate(p,goal)
            good = out["status"]=="generated" and interpret(out["text"])==row["meaning"] and text_goal(out["text"])==goal
            count(c,"generate",out["status"]=="generated",good)
            outputs.append({"goal":goal,"status":out["status"],"output":out.get("text"),"reason":out.get("reason"),"exact":good})
        records.append({"input_for_evaluator_only":row["text"],"expected":row["meaning"],"source_status":"read","recovery_status":recovered["status"],"recovered":recovered.get("meaning"),"recovery_reason":recovered.get("reason"),"outputs":outputs})
    c["end_to_end_generate_requests"] = len(data(split))*len(GOALS)
    c["end_to_end_generate_exact"] = c["generate_exact"]
    return {"counts":c,"records":records,"fingerprint":model.fingerprint}


def memory_load(dimension,load,seed):
    """Microbenchmark of unchanged ProjectionMemory, NOT extra language facts."""
    book, observations = Book(dimension,seed), [({"address":f"known:{i}"},f"label:{i%8}") for i in range(load)]
    memory,stats = fit_memory(Space(book),observations,partial=False)
    c,records = empty_counts(("known","missing")),[]
    for context,expected in observations + [({"address":f"missing:{i}"},None) for i in range(64)]:
        out = memory.recall(context)
        accepted = out["value"] is not None
        category = "known" if expected is not None else "missing"
        # exact is successful retrieval only. Correct absence is separately counted.
        exact = accepted and expected is not None and out["value"]==expected
        count(c,category,accepted,exact)
        records.append({"query":context,"expected":expected,"recalled":out["value"],"projections":out["projections"]})
    c["missing_correct_rejection"] = c["missing_abstained"]
    table={canonical(context):label for context,label in observations}
    table_correct=sum(table.get(canonical(context))==label for context,label in observations)
    table_missing=sum(table.get(canonical({"address":f"missing:{i}"})) is None for i in range(64))
    return {"dimension":dimension,"load":load,"seed":seed,"counts":c,"statistics":stats,"records":records,
            "table_reference":{"known_exact":table_correct,"known_requests":load,"missing_correct_rejection":table_missing,"missing_requests":64},
            "scope":"Same eight candidates; load distinct address/label associations. Exact ordinary dictionary control; no matched byte or time budget."}
````

## `memory_bench.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/memory_bench.py`  
SHA256: `faece53383254c56bec30a0e9bab68dc4545b92616c0f65a2e5de36ecb057a8a`

````python
"""Isolated address/label association; never a larger language task."""
import hashlib
import sys
import tracemalloc
from plm_l1_v06.algebra import canonical
from plm_l1_v06.banked import fit_banked, route, META_BYTES
from measurements import count, empty_counts


def deep_size(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    total = sys.getsizeof(value)
    if isinstance(value, dict):
        total += sum(deep_size(k,seen)+deep_size(v,seen) for k,v in value.items())
    elif isinstance(value, (tuple,list)):
        total += sum(deep_size(v,seen) for v in value)
    return total


def addresses(load, scenario):
    if scenario == "ordinary":
        return ["known:"+str(i) for i in range(load)]
    result, i = [], 0
    while len(result) < load:
        key = "collision:"+str(i)
        if route({"address":key},8) == 0:
            result.append(key)
        i += 1
    return result


def measure(dimension, load, seed, modes, missing_count, scenario="ordinary"):
    observations = [({"address":key},"label:"+str(i%8)) for i,key in enumerate(addresses(load,scenario))]
    missing = [({"address":"missing:"+str(i)},None) for i in range(missing_count)]
    methods, telemetry = {}, {}
    for mode in modes:
        memory,stats = fit_banked(observations,dimension,seed,partial=False,mode=mode,cache_slots=0)
        c,records = empty_counts(("known","missing")),[]
        for context,expected in observations+missing:
            out = memory.recall(context)
            accepted = out["value"] is not None
            prefix = "known" if expected is not None else "missing"
            count(c,prefix,accepted,accepted and expected is not None and out["value"]==expected)
            records.append({"query":context,"expected":expected,"recalled":out["value"],"projections":out["projections"]})
        c["missing_correct_rejection"] = c["missing_abstained"]
        methods[mode] = {"counts":c,"statistics":stats,"records":records,"weight_digest":hashlib.sha256(b"".join(b.blob[META_BYTES:] for b in memory.blocks)).hexdigest()}
        tracemalloc.start()
        memory.recall(missing[0][0])
        _,peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        telemetry[mode] = {"traced_peak_query_allocation_bytes":peak,"scope":"One uncached missing query; Python/NumPy traced allocations, not process RSS or hard upper bound."}
    table = {canonical(c):v for c,v in observations}
    return {"dimension":dimension,"load":load,"seed":seed,"scenario":scenario,"methods":methods,
            "table_reference":{"known_exact":sum(table.get(canonical(c))==v for c,v in observations),"known_requests":load,
                               "missing_correct_rejection":sum(table.get(canonical(c)) is None for c,_ in missing),"missing_requests":missing_count,"owned_heap_bytes":deep_size(table),"budget_matched":False}},telemetry
````

## `plm_l1_v06/__init__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/__init__.py`  
SHA256: `8f05c473108f28e82f66110c2c81924843fd68b7c4b9de5dfd6e67c695fb0443`

````python
"""PLM-L1 0.6.0: fixed-budget banked phase memory with pair evidence."""
__version__ = "0.6.0"
````

## `plm_l1_v06/__main__.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/__main__.py`  
SHA256: `b8715e93ef6cc78dd544f964627fab26e483bfff6949fd630e6fde150815d088`

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
    fit.add_argument("--seed", default="banked-development-0")
    fit.add_argument("--memory-mode", choices=("single", "split", "proof", "split_proof", "split_unchecked"), default="split_proof")
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
            model = fit(load(args.pairs), load(args.lexicon), seed=args.seed, dimension=args.dimension, memory_mode=args.memory_mode)
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

## `plm_l1_v06/algebra.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/algebra.py`  
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

## `plm_l1_v06/banked.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/banked.py`  
SHA256: `e1841b8961ffe8e0839286d3ed4c560f0c785ebe1ab922e15d3bb2458749b90d`

````python
"""Fixed-budget phase memory: projected-key routing and pair evidence.

Each immutable block owns only a padded byte string containing metadata and
complex128 weights. No stored key list, membership set, tree or code cache.
The optional inference cache is a fixed-size bytearray, never serialized.
"""
import hashlib
import json
import struct
import sys
import numpy as np
from .algebra import canonical, require
from .projection import structure_code, dependency_leaves

MODES = {"single":0,"split":1,"proof":2,"split_proof":3,"split_unchecked":4}
META_BYTES = 2048
CACHE_SLOTS = 32
CACHE_SLOT_BYTES = 4096


class FreshBook:
    """Same phase generator as algebra.Book, arbitrary internal width, no cache."""
    __slots__ = ("dimension","seed")
    def __init__(self,dimension,seed):
        self.dimension,self.seed=dimension,seed
    def code(self,namespace,value):
        key=canonical(["plm-l1-phase-u53-v1",self.seed,namespace,value])
        raw=hashlib.shake_256(key.encode("utf-8")).digest(8*self.dimension)
        phase=(np.frombuffer(raw,dtype="<u8")>>11).astype(float)*(2.**-53)*(2*np.pi)
        return np.exp(1j*phase)


def key_code(book,fields):
    out=book.code("field_set",sorted(fields))
    for field in sorted(fields):
        out*=structure_code(book,fields[field],"field:"+field)
    return out


def value_code(book,label):
    try:
        value=json.loads(label)
    except (json.JSONDecodeError,TypeError):
        value=label
    return book.code("target_namespace","target")*structure_code(book,value)


def route(key,banks):
    return int.from_bytes(hashlib.sha256(canonical(["plm-routing-v1",key]).encode("utf-8")).digest()[:8],"little")%banks


def bank_count(load,budget,mode):
    if mode not in (1,3,4):
        return 1
    banks=1
    while load>8*banks and banks<8 and budget//(2*banks)>=128:
        banks*=2
    return banks


def bank_seed(seed,index,banks):
    return seed if banks==1 else seed+"/bank:"+str(index)


class MemoryBlock:
    __slots__=("_blob",)
    def __init__(self,blob):
        require(type(blob) is bytes and len(blob)>META_BYTES,"invalid_block")
        n=struct.unpack_from("<I",blob)[0]
        require(0<n<=META_BYTES-4,"invalid_block_header")
        meta=json.loads(blob[4:4+n].decode("utf-8"))
        required={"schema","seed","budget","mode","mask","candidates","banks","counts","value_width","proof_width"}
        require(set(meta)==required and meta["schema"]=="plm-banked-block-v1","invalid_block_metadata")
        require(type(meta["budget"]) is int and 128<=meta["budget"]<=16384 and meta["budget"]%128==0,"invalid_block_budget")
        require(type(meta["mode"]) is int and meta["mode"] in MODES.values(),"invalid_block_mode")
        require(meta["banks"] in (1,2,4,8) and len(meta["counts"])==meta["banks"],"invalid_banks")
        require(all(type(c) is int and c>=0 for c in meta["counts"]) and 0<sum(meta["counts"])<=256,"invalid_load")
        require(meta["value_width"]>0 and meta["proof_width"]>=0 and meta["banks"]*(meta["value_width"]+meta["proof_width"])==meta["budget"],"invalid_layout")
        require(meta["proof_width"]==(meta["budget"]//meta["banks"]//4 if meta["mode"] in (2,3,4) else 0),"invalid_proof_layout")
        require(meta["mask"]==sorted(set(meta["mask"])) and all(type(s) is str for s in meta["mask"]),"invalid_mask")
        require(meta["candidates"]==sorted(set(meta["candidates"])) and bool(meta["candidates"]) and all(type(s) is str for s in meta["candidates"]),"invalid_candidates")
        require(meta["banks"]==bank_count(sum(meta["counts"]),meta["budget"],meta["mode"]),"invalid_bank_policy")
        require(type(meta["seed"]) is str and 0<len(meta["seed"])<=128,"invalid_seed")
        require(len(blob)==META_BYTES+16*meta["budget"] and not any(blob[4+n:META_BYTES]),"invalid_block_size_or_padding")
        require(np.isfinite(np.frombuffer(blob,dtype="<c16",offset=META_BYTES)).all(),"invalid_block_weights")
        self._blob=blob
    @property
    def blob(self):
        return self._blob
    def meta(self):
        n=struct.unpack_from("<I",self.blob)[0]
        return json.loads(self.blob[4:4+n].decode("utf-8"))
    def recall(self,context):
        m=self.meta()
        require(all(f in context for f in m["mask"]),"missing_query_field")
        key={f:context[f] for f in m["mask"]}
        bank=route(key,m["banks"])
        dv,dp=m["value_width"],m["proof_width"]
        weights=np.frombuffer(self.blob,dtype="<c16",offset=META_BYTES)
        start=bank*(dv+dp)
        book=FreshBook(dv,bank_seed(m["seed"],bank,m["banks"]))
        query=weights[start:start+dv]*key_code(book,key)
        scores=np.array([float(np.vdot(value_code(book,c),query).real/dv) for c in m["candidates"]])
        order=np.argsort(-scores,kind="stable")
        top=float(scores[order[0]])
        runner=max(0.,float(scores[order[1]])) if len(order)>1 else 0.
        candidate=m["candidates"][order[0]]
        good=top>=.65 and top-runner>=.25
        evidence=None
        if dp:
            proof=FreshBook(dp,bank_seed(m["seed"],bank,m["banks"])+"/pair-evidence")
            expected=proof.code("key_value_pair",[key,candidate])
            evidence=float(np.vdot(expected,weights[start+dv:start+dv+dp]).real/dp)
            if m["mode"] in (2,3):
                good=good and evidence>=.65
        return {"mask":m["mask"],"bank":bank,"bank_load":m["counts"][bank],"banks":m["banks"],
                "value":candidate if good else None,"score":round(top,8),"margin":round(top-runner,8),
                "evidence":None if evidence is None else round(evidence,8),"evidence_required":m["mode"] in (2,3)}


class BankedMemory:
    __slots__=("blocks","cache")
    def __init__(self,blocks,cache_slots=CACHE_SLOTS):
        require(type(cache_slots) is int and cache_slots in (0,CACHE_SLOTS),"invalid_cache_size")
        self.blocks=tuple(blocks)
        require(bool(self.blocks),"empty_memory")
        self.cache=bytearray(cache_slots*CACHE_SLOT_BYTES)
    def recall(self,context):
        fields=sorted({f for b in self.blocks for f in b.meta()["mask"]})
        require(all(f in context for f in fields),"missing_query_field")
        identity=canonical({f:context[f] for f in fields})
        slot=None
        if self.cache:
            index=int.from_bytes(hashlib.sha256(identity.encode("utf-8")).digest()[:8],"little")%CACHE_SLOTS
            slot=index*CACHE_SLOT_BYTES
            n=struct.unpack_from("<I",self.cache,slot)[0]
            if n:
                cached=json.loads(self.cache[slot+4:slot+4+n])
                if cached[0]==identity:
                    return cached[1]
        audits=[b.recall(context) for b in self.blocks]
        accepted={a["value"] for a in audits if a["value"] is not None}
        result={"value":next(iter(accepted)) if len(accepted)==1 else None,
                "reason":"recalled" if len(accepted)==1 else "weak_unregistered_or_conflicting_projection","projections":audits}
        if slot is not None:
            payload=canonical([identity,result]).encode("utf-8")
            if len(payload)<=CACHE_SLOT_BYTES-4:
                self.cache[slot:slot+CACHE_SLOT_BYTES]=struct.pack("<I",len(payload))+payload+b"\0"*(CACHE_SLOT_BYTES-4-len(payload))
        return result
    def clear_cache(self):
        self.cache[:]=b"\0"*len(self.cache)
    def storage(self):
        return {"state_bytes":sum(len(b.blob) for b in self.blocks),"cache_capacity_bytes":len(self.cache),
                "owned_heap_bytes":sys.getsizeof(self)+sys.getsizeof(self.blocks)+sys.getsizeof(self.cache)+sum(sys.getsizeof(b)+sys.getsizeof(b.blob) for b in self.blocks),
                "numerical_weight_bytes":sum(16*b.meta()["budget"] for b in self.blocks)}


def fit_banked(observations,dimension,seed,*,partial=True,enabled=True,mode="split_proof",cache_slots=CACHE_SLOTS):
    require(type(mode) is str and mode in MODES and type(dimension) is int and 128<=dimension<=16384 and dimension%128==0,"invalid_memory_settings")
    require(type(enabled) is bool and type(seed) is str and 0<len(seed)<=128,"invalid_memory_settings")
    leaves=dependency_leaves(observations,partial)
    require(len(leaves)<=256,"memory_capacity_exceeded")
    masks=sorted({tuple(sorted(c)) for c,_ in leaves})
    blocks=[]
    for mask in masks:
        selected=sorted([(c,t) for c,t in leaves if tuple(sorted(c))==mask],key=canonical)
        banks=bank_count(len(selected),dimension,MODES[mode])
        dp=dimension//banks//4 if MODES[mode] in (2,3,4) else 0
        dv=dimension//banks-dp
        vector=np.zeros(dimension,dtype="<c16")
        counts=[0]*banks
        for context,label in selected:
            bank=route(context,banks)
            counts[bank]+=1
            if enabled:
                book=FreshBook(dv,bank_seed(seed,bank,banks))
                start=bank*(dv+dp)
                vector[start:start+dv]+=key_code(book,context).conj()*value_code(book,label)
                if dp:
                    proof=FreshBook(dp,bank_seed(seed,bank,banks)+"/pair-evidence")
                    vector[start+dv:start+dv+dp]+=proof.code("key_value_pair",[context,label])
        meta={"schema":"plm-banked-block-v1","seed":seed,"budget":dimension,"mode":MODES[mode],"mask":list(mask),
              "candidates":sorted({t for _,t in selected}),"banks":banks,"counts":counts,"value_width":dv,"proof_width":dp}
        payload=canonical(meta).encode("utf-8")
        require(len(payload)<=META_BYTES-4,"metadata_capacity_exceeded")
        blob=struct.pack("<I",len(payload))+payload+b"\0"*(META_BYTES-4-len(payload))+vector.tobytes()
        blocks.append(MemoryBlock(blob))
    memory=BankedMemory(blocks,cache_slots)
    stats={"observations":len(observations),"complete_contexts":len({canonical(c) for c,_ in observations}),
           "projected_contexts":len(leaves),"masks":[list(m) for m in masks],"groups":len(blocks),
           "bank_counts":[b.meta()["banks"] for b in blocks],"bank_loads":[b.meta()["counts"] for b in blocks],**memory.storage()}
    return memory,stats
````

## `plm_l1_v06/features.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/features.py`  
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

## `plm_l1_v06/lexicon.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/lexicon.py`  
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

## `plm_l1_v06/projection.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/projection.py`  
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

## `plm_l1_v06/reader.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/reader.py`  
SHA256: `7741a41ba0b3e2f0966eefebe82106552918aa262a2a9d5617d973a04a6e1b7d`

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
        # Check our own candidate, never an evaluator's gold meaning. This
        # certifies signal consistency only, not external semantic correctness.
        packet = model.encode(meaning)
        recovered = model.recover(packet)
        if recovered["status"] != "recovered":
            return abstain("meaning_signal_unrecoverable", recovery_reason=recovered.get("reason"))
        if recovered["meaning"] != meaning:
            return abstain("meaning_signal_mismatch")
        return {"status": "read", "packet": packet, "audit": audit,
                "signal_verified": True, "verification": {"method": "recover_equals_candidate", "residual": recovered.get("residual")},
                "eligible_for_inference": False}
    except (ValueError, TypeError) as error:
        return abstain(str(error))
````

## `plm_l1_v06/runtime.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/runtime.py`  
SHA256: `03885e8a138a974a822b2a7e5e767546977631e4d3e19f2b2cea59b24a3d7f0f`

````python
"""Signal codec and learned component assembly; no reader/trainer imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require
from .lexicon import CONTENT, ROLES, GOALS, validate_meaning
from .features import START, gap_context
from .banked import BankedMemory, MemoryBlock, MODES

MEMORIES = ("roles", "polarity", "modality", "order_support", "order_output", "gaps", "lexical_read", "lexical_write")


def abstain(reason, **extra):
    return {"status": "abstain", "reason": reason, "text": None, "packet": None, "eligible_for_inference": False, **extra}


class Model:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-banked-v1" and self.meta.get("eligible_for_inference") is False, "invalid_metadata")
        require(self.meta.get("memory_mode") in MODES, "invalid_memory_mode")
        require(self.meta.get("read_acceptance") == "recover_equals_candidate_v1", "invalid_read_acceptance_policy")
        require(set(memories) == set(MEMORIES) and set(self.meta["slot_candidates"]) == set(ROLES), "invalid_inventory")
        self.memories = memories
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        for memory in memories.values():
            require(isinstance(memory, BankedMemory), "invalid_memory_type")
            for block in memory.blocks:
                m = block.meta()
                require(m["seed"] == self.meta["seed"] and m["budget"] == self.meta["dimension"] and m["mode"] == MODES[self.meta["memory_mode"]], "block_model_mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {name: [hashlib.sha256(b.blob).hexdigest() for b in memory.blocks] for name, memory in sorted(memories.items())}})
        self.basis = {r: np.array([self.book.code("value", v).conj() for v in self.meta["slot_candidates"][r]]) for r in ROLES}

    def encode(self, meaning):
        validate_meaning(meaning, self.meta["slot_candidates"])
        vector = sum(self.book.code("semantic_role", r) * self.book.code("value", meaning[r]) for r in ROLES)
        return {"schema": "plm-l1-banked-meaning-v1", "model_fingerprint": self.fingerprint, "dimension": self.book.dimension,
                "real": vector.real.tolist(), "imag": vector.imag.tolist(), "eligible_for_inference": False}

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
            require(packet["schema"] == "plm-l1-banked-meaning-v1" and packet["model_fingerprint"] == self.fingerprint, "packet_model_mismatch")
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
            for i, block in enumerate(memory.blocks):
                key = name + "_" + str(i)
                groups[name].append({"weight": key})
                weights[key] = np.frombuffer(block.blob, dtype=np.uint8)
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
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            expected = {g["weight"] for groups in info["groups"].values() for g in groups}
            require(expected == set(weights.files), "invalid_weight_inventory")
            require(all(set(g) == {"weight"} for groups in info["groups"].values() for g in groups), "invalid_block_inventory")
            require(all(weights[k].dtype == np.uint8 and weights[k].ndim == 1 for k in expected), "invalid_block_encoding")
            memories = {name: BankedMemory([MemoryBlock(weights[g["weight"]].tobytes()) for g in groups]) for name, groups in info["groups"].items()}
        model = cls(meta, memories)
        require(model.fingerprint == info["fingerprint"], "model_hash_mismatch")
        return model
````

## `plm_l1_v06/training.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/plm_l1_v06/training.py`  
SHA256: `55acea5cfea7bbc3cc9a9b235f48928a6b0af4c92d25b553f6c4279257b0fd93`

````python
"""Only text/meaning pairs and explicit initial lexicon enter this learner."""
from .algebra import Book, canonical, digest, require
from .features import observations
from .banked import fit_banked
from .runtime import Model


def fit(pairs, lexicon, *, seed="banked-development-0", dimension=8192, partial=True, learning=True, memory_mode="split_proof"):
    require(type(partial) is bool and type(learning) is bool, "invalid_switches")
    rows = observations(pairs, lexicon)
    Book(dimension, seed)
    memories, statistics = {}, {}
    for name, values in rows.items():
        memories[name], statistics[name] = fit_banked(values, dimension, seed, partial=partial, enabled=learning or name.startswith("lexical_"), mode=memory_mode)
    meta = {"schema": "plm-l1-banked-v1", "memory_mode": memory_mode, "read_acceptance": "recover_equals_candidate_v1", "seed": seed, "dimension": dimension, "partial": partial, "learning": learning,
            "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)), "lexicon_digest": digest(lexicon),
            "kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"],
            "statistics": statistics, "supervision_fields": ["text", "meaning"], "supplied_trace_supervision": False,
            "dependency_selection": "deterministic categorical information gain during training only", "eligible_for_inference": False}
    return Model(meta, memories)
````

## `release_tools.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/release_tools.py`  
SHA256: `ea08f662c4f46adf6aaab3e06dfbc70bfe018019f7dacece0e7beca7548f1cbb`

````python
"""Additive source freezing, prior-release preservation, examples and ZIP."""
import argparse
import hashlib
import json
import zipfile
from evaluate import ROOT, source_files, verify_freeze
from evaluation_support import V05
from plm_l1_v06.algebra import digest
from plm_l1_v06.runtime import Model


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
        manifest = {"schema": "plm-l1-v06-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif command == "check-baseline":
        files = []
        for name in ("PLM-L1-v0.1", "PLM-L1-v0.2", "PLM-L1-v0.3", "PLM-L1-v0.4", "PLM-L1-v0.5", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        baseline = json.loads((ROOT / "verification" / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        if hashes(files, ROOT.parent) != baseline:
            raise ValueError("old release changed")
        source = ROOT.parent / "PLM-L1-v0.5"
        vendor_files = [p for p in V05.rglob("*") if p.is_file()]
        if hashes([p for p in source.rglob("*") if p.is_file()], source) != hashes(vendor_files, V05):
            raise ValueError("vendored v0.5 changed")
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
        verification = json.loads((ROOT / "verification" / "REPRODUCIBILITY.json").read_text(encoding="utf-8"))
        if verification["status"] != "passed" or verification["complete_numeric_runs"] != 2:
            raise ValueError("completed reproducibility verification required")
        archive = ROOT.parent / "PLM-L1-v0.6.zip"
        checksum_path = ROOT.parent / "PLM-L1-v0.6.sha256"
        if archive.exists() or checksum_path.exists():
            raise ValueError("release archive already exists")
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0] != "work")
        write(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v06-release-v1", "files": hashes(files, ROOT)})
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

## `report.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/report.py`  
SHA256: `df19f37f3a5f8d1d81edc7298894a3c86373643e576e83191e55dc503bd0612c`

````python
"""Derived tables, including coverage loss; no result-dependent gate changes."""
from pathlib import Path


def aggregate(rows,mode):
    keys=("known_requests","known_exact","known_wrong","known_abstained","missing_requests","missing_accepted")
    return {k:sum(r["methods"][mode]["counts"][k] for r in rows) for k in keys}


def write_report(output,result):
    lines=["# PLM-L1 v0.6 評価結果", "", "固定予算の記憶サブシステム比較。未登録照会の拒否率と、登録照会の正答・誤答・保留を分けて評価する。", "",
           "## 言語試験", "", "|方式|未学習組合せ・読解|未学習組合せ・生成|両側未学習・往復|全往復|", "|---|---:|---:|---:|---:|"]
    for mode in ("single","split_proof","split_unchecked"):
        cells=[]
        for bucket in ("read_heldout","generate_heldout","roundtrip_both_heldout","roundtrip_other"):
            cs=[r["methods"][mode]["counts"] for r in result["standard"]]
            keys=(bucket,) if bucket!="roundtrip_other" else ("roundtrip_both_heldout","roundtrip_other")
            cells.append(str(sum(c[k+"_exact"] for c in cs for k in keys))+"/"+str(sum(c[k+"_requests"] for c in cs for k in keys)))
        lines.append("|"+mode+"|"+"|".join(cells)+"|")
    ordinary=[r for r in result["memory"] if r["scenario"]=="ordinary"]
    lines += ["", "## 独立記憶試験・通常のキー分布（全負荷合算）", "", "|方式|登録照会数|正答|誤答|保留|未登録照会の誤受理|", "|---|---:|---:|---:|---:|---:|"]
    for mode in ("single","split","proof","split_proof","split_unchecked"):
        c=aggregate(ordinary,mode)
        lines.append(f'|{mode}|{c["known_requests"]}|{c["known_exact"]}|{c["known_wrong"]}|{c["known_abstained"]}|{c["missing_accepted"]}/{c["missing_requests"]}|')
    a,b=aggregate(ordinary,"split_proof"),aggregate(ordinary,"single")
    lines += ["", f'未登録誤受理の合算減少率：{100*(1-a["missing_accepted"]/max(1,b["missing_accepted"])):.1f}%。登録正答の維持率：{100*a["known_exact"]/max(1,b["known_exact"]):.1f}%（single比）。',
              "", "これは異なる負荷条件を等しい試行構成で合算した値であり、運用時のエラー確率や統計的有意性ではない。負荷ごとの数値を以下に残す。", "",
              "|分布|D|N|方式|正答|誤答|保留|未登録誤受理|", "|---|---:|---:|---|---:|---:|---:|---:|"]
    groups=sorted({(r["scenario"],r["dimension"],r["load"]) for r in result["memory"]})
    for scenario,d,n in groups:
        rows=[r for r in result["memory"] if (r["scenario"],r["dimension"],r["load"])==(scenario,d,n)]
        for mode in ("single","split","proof","split_proof","split_unchecked"):
            c=aggregate(rows,mode)
            lines.append(f'|{scenario}|{d}|{n}|{mode}|{c["known_exact"]}/{c["known_requests"]}|{c["known_wrong"]}|{c["known_abstained"]}|{c["missing_accepted"]}/{c["missing_requests"]}|')
    lines += ["", "## 判定と限界", "", f'固定判定：{sum(c["passed"] for c in result["checks"])}/{len(result["checks"])}。開発実行には合否判定を付けない。',
              "", "確認信号は誤受理を抑えるが、値記憶の次元を消費し、正答を保留に変える場合がある。分割単独の改善、全負荷での容量改善、誤受理ゼロは保証しない。意図的に同じバンクへ衝突させたケースも省略しない。",
              "", "同一予算は記憶ブロック・付随メタデータ予約領域・固定推論キャッシュ・それらのPythonオブジェクトに限定する。意味コーデック、Model側統計、インタプリタ、照会中の一時割当は含めない。TELEMETRY.jsonに時間とtracemallocの一時割当を別記し、結果ハッシュから除く。通常辞書は同じ照会を解く参考実装だが、予算を揃えていない。",
              "", "言語試験は既存の限定一事象・五スロット文法。記憶試験のN増加は言語知識の拡張ではない。ID3型の依存特徴選択、文字列処理、ルーティング、制御は通常Python。明示チップ列の拡散・逆拡散や同期との接続は未実装。", ""]
    (Path(output)/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
````

## `requirements.txt`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/requirements.txt`  
SHA256: `7bd6b8946940b79948c548c8048e545684b91c8edc9444d8dfc0c8f76a97c0a7`

````text
numpy==2.3.5
````

## `tests/test_banked.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/tests/test_banked.py`  
SHA256: `449bc1fa0ed553be58eee8ea9983705504979700b290fdc0443a6567489a599e`

````python
import copy
import hashlib
import json
import struct
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import Book,canonical
from plm_l1_v06.banked import (BankedMemory,MemoryBlock,FreshBook,MODES,META_BYTES,CACHE_SLOT_BYTES,CACHE_SLOTS,
                              fit_banked,bank_count,bank_seed,key_code,value_code,route)
from plm_l1_v06.projection import Space,fit_memory
from plm_l1_v06.training import fit
from plm_l1_v06.runtime import Model
from evaluation_support import data,train_for,interpret
from measurements import count,empty_counts
from memory_bench import measure


def observations(n=32):
    return [({"address":"dev:"+str(i)},"label:"+str(i%8)) for i in range(n)]


def make(mode="split_proof",n=32,d=512,cache=0):
    return fit_banked(observations(n),d,"banked-unit-0",partial=False,mode=mode,cache_slots=cache)[0]


class BankedTests(unittest.TestCase):
    def test_exact_budget_all_five_modes(self):
        for d in (128,512,2048):
            sizes=[make(mode,d=d).storage() for mode in MODES]
            self.assertTrue(all(s==sizes[0] for s in sizes))
            self.assertEqual(sizes[0]["state_bytes"],META_BYTES+16*d)

    def test_fixed_cache_budget_after_queries(self):
        memory=make(cache=CACHE_SLOTS)
        before=memory.storage()
        for i in range(128):
            memory.recall({"address":"missing:"+str(i)})
        self.assertEqual(before,memory.storage())
        self.assertEqual(before["cache_capacity_bytes"],CACHE_SLOT_BYTES*CACHE_SLOTS)

    def test_cache_result_mutation_cannot_poison(self):
        m=make(n=8,d=2048,cache=CACHE_SLOTS)
        q=observations(1)[0][0]
        original=m.recall(q)
        expected=copy.deepcopy(original)
        original["value"]="tampered"
        original["projections"][0]["score"]=-99
        self.assertEqual(m.recall(q),expected)

    def test_cache_and_cold_answers_identical(self):
        a,b=make(cache=CACHE_SLOTS),make(cache=0)
        for c,_ in observations()+[({"address":"unknown"},None)]:
            self.assertEqual(a.recall(c),b.recall(c))
            self.assertEqual(a.recall(c),b.recall(c))
        a.clear_cache()
        self.assertFalse(any(a.cache))

    def test_no_persistent_codebook_or_key_table(self):
        m=make()
        self.assertFalse(hasattr(m,"__dict__"))
        self.assertEqual(BankedMemory.__slots__,("blocks","cache"))
        for b in m.blocks:
            self.assertFalse(hasattr(b,"__dict__"))
            self.assertNotIn("dev:",canonical(b.meta()))

    def test_readonly_blob_public_interface(self):
        b=make().blocks[0]
        with self.assertRaises(AttributeError):
            b.blob=b.blob

    def test_banks_adapt_only_to_projected_load_and_budget(self):
        self.assertEqual([bank_count(n,8192,3) for n in (8,9,16,17,32,33,256)],[1,2,2,4,4,8,8])
        self.assertEqual(bank_count(256,128,3),1)
        self.assertEqual(bank_count(256,512,3),4)
        self.assertEqual(bank_count(256,8192,0),1)

    def test_proof_weights_in_total_budget(self):
        for mode in MODES:
            b=make(mode).blocks[0]
            m=b.meta()
            self.assertEqual(m["banks"]*(m["value_width"]+m["proof_width"]),512)
            self.assertEqual(m["proof_width"]>0,mode in ("proof","split_proof","split_unchecked"))

    def test_evidence_ablation_identical_numerical_arrays(self):
        a,b=make("split_proof"),make("split_unchecked")
        self.assertEqual(a.blocks[0].blob[META_BYTES:],b.blocks[0].blob[META_BYTES:])
        for c,_ in observations(128):
            x,y=a.recall(c),b.recall(c)
            self.assertEqual(x["projections"][0]["score"],y["projections"][0]["score"])
            if x["value"] is not None:
                self.assertEqual(x["value"],y["value"])

    def test_single_matches_legacy_value_equations(self):
        obs=observations()
        old,_=fit_memory(Space(Book(512,"banked-unit-0")),obs,partial=False)
        new=make("single")
        np.testing.assert_array_equal(old.groups[0][1],np.frombuffer(new.blocks[0].blob,dtype="<c16",offset=META_BYTES))
        for c,_ in observations(64):
            a,b=old.recall(c),new.recall(c)
            self.assertEqual(a["value"],b["value"])
            self.assertEqual(a["projections"][0]["score"],b["projections"][0]["score"])

    def test_partial_key_routes_novel_combinations(self):
        obs=[({"part":str(i),"nuisance":n},str(i%2)) for i in range(16) for n in ("a","b")]
        memory,stats=fit_banked(obs,8192,"banked-unit-0",cache_slots=0)
        self.assertEqual(stats["masks"],[["part"]])
        self.assertGreater(stats["bank_counts"][0],1)
        for i in range(16):
            a=memory.recall({"part":str(i),"nuisance":"a"})
            b=memory.recall({"part":str(i),"nuisance":"never_seen_combination"})
            self.assertEqual(a,b)
            self.assertEqual(a["value"],str(i%2))
        self.assertIsNone(memory.recall({"part":"unregistered","nuisance":"a"})["value"])

    def test_routing_does_not_use_labels(self):
        obs=observations()
        a,_=fit_banked(obs,512,"banked-unit-0",partial=False)
        b,_=fit_banked([(c,"other:"+t) for c,t in obs],512,"banked-unit-0",partial=False)
        self.assertEqual(a.blocks[0].meta()["counts"],b.blocks[0].meta()["counts"])

    def test_pair_evidence_is_key_and_value_specific(self):
        book=FreshBook(2048,"unit-evidence")
        a=book.code("key_value_pair",[{"x":"a"},"v1"])
        b=book.code("key_value_pair",[{"x":"b"},"v1"])
        c=book.code("key_value_pair",[{"x":"a"},"v2"])
        self.assertLess(abs(np.vdot(a,b).real/2048),.15)
        self.assertLess(abs(np.vdot(a,c).real/2048),.15)

    def test_zero_evidence_rejects_same_value_recall(self):
        block=make(n=8,d=2048).blocks[0]
        m=block.meta()
        v=np.frombuffer(block.blob,dtype="<c16",offset=META_BYTES).copy()
        v[m["value_width"]:]=0
        changed=MemoryBlock(block.blob[:META_BYTES]+v.tobytes())
        self.assertIsNotNone(block.recall(observations(1)[0][0])["value"])
        self.assertIsNone(changed.recall(observations(1)[0][0])["value"])

    def test_wrong_value_not_validated_by_key_only(self):
        obs=[({"address":"first"},"one"),({"address":"second"},"two")]
        mem,_=fit_banked(obs,8192,"unit-pair",partial=False,mode="proof",cache_slots=0)
        b=mem.blocks[0]; m=b.meta()
        v=np.frombuffer(b.blob,dtype="<c16",offset=META_BYTES).copy()
        book=FreshBook(m["value_width"],m["seed"])
        v[:m["value_width"]]=key_code(book,obs[0][0]).conj()*value_code(book,"two")
        r=MemoryBlock(b.blob[:META_BYTES]+v.tobytes()).recall(obs[0][0])
        self.assertGreater(r["score"],.99)
        self.assertLess(r["evidence"],.2)
        self.assertIsNone(r["value"])

    def test_overload_still_has_false_accepts(self):
        m,_=fit_banked(observations(128),128,"banked-development-0",partial=False,cache_slots=0)
        self.assertGreater(sum(m.recall({"address":"absent-dev:"+str(i)})["value"] is not None for i in range(128)),0)

    def test_invalid_dimension_mode_and_cache_rejected(self):
        for kwargs in ({"dimension":192},{"dimension":True},{"mode":[]},{"mode":"unknown"},{"cache_slots":1}):
            options=dict(dimension=512,seed="unit",partial=False)
            options.update(kwargs)
            with self.assertRaises(ValueError):
                fit_banked(observations(),**options)

    def test_missing_query_field_rejected(self):
        with self.assertRaises(ValueError):
            make().recall({})

    def test_invalid_block_padding_length_and_weights(self):
        b=make().blocks[0].blob
        variants=[b[:-1],b[:META_BYTES-1]+b"x"+b[META_BYTES:],b[:META_BYTES]+np.full(512,np.nan,dtype="<c16").tobytes()]
        for blob in variants:
            with self.assertRaises(ValueError):
                MemoryBlock(blob)

    def test_no_query_time_learning_or_adaptation(self):
        m=make()
        before=m.blocks[0].blob
        with patch("plm_l1_v06.banked.dependency_leaves",side_effect=AssertionError()):
            for i in range(100):
                m.recall({"address":"unknown:"+str(i)})
        self.assertEqual(before,m.blocks[0].blob)

    def test_multi_mask_conflicting_values_abstain(self):
        a,_=fit_banked([({"x":"k"},"a")],2048,"unit",cache_slots=0)
        b,_=fit_banked([({"y":"k"},"b")],2048,"unit",cache_slots=0)
        self.assertIsNone(BankedMemory(a.blocks+b.blocks,0).recall({"x":"k","y":"k"})["value"])

    def test_count_denominators(self):
        c=empty_counts(("known","missing"))
        for accepted,exact in ((True,True),(True,False),(False,False)):
            count(c,"known",accepted,exact)
        count(c,"missing",False,False)
        self.assertEqual([c["known_"+k] for k in ("requests","exact","wrong","abstained")],[3,1,1,1])
        self.assertEqual(c["missing_exact"],0)

    def test_benchmark_includes_wrong_and_missing_records(self):
        r,_=measure(128,8,"unit",list(MODES),8)
        for method in r["methods"].values():
            c=method["counts"]
            self.assertEqual(len(method["records"]),16)
            self.assertEqual(c["known_exact"]+c["known_wrong"]+c["known_abstained"],8)
            self.assertEqual(c["missing_accepted"]+c["missing_correct_rejection"],8)


class SignalGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=fit(train_for("object_negative"),data("lexicon"))
        cls.text="花子を太郎が助けなかった。"

    def test_unrecoverable_own_candidate_abstains(self):
        with patch.object(Model,"recover",return_value={"status":"abstain","reason":"unit_failure"}):
            r=self.model.read(self.text)
        self.assertEqual(r["reason"],"meaning_signal_unrecoverable")
        self.assertIsNone(r["packet"])

    def test_different_recovered_meaning_abstains(self):
        m=interpret(self.text)
        m["subject"],m["object"]=m["object"],m["subject"]
        with patch.object(Model,"recover",return_value={"status":"recovered","meaning":m}):
            r=self.model.read(self.text)
        self.assertEqual(r["reason"],"meaning_signal_mismatch")

    def test_inference_cannot_use_training_selector(self):
        with patch("plm_l1_v06.banked.dependency_leaves",side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.model.read(self.text)["packet"])["text"],self.text)

    def test_language_fixed_memory_budget(self):
        sizes=[]
        for mode in MODES:
            m=fit(train_for("object_negative"),data("lexicon"),memory_mode=mode)
            sizes.append(sum(mem.storage()["owned_heap_bytes"] for mem in m.memories.values()))
        self.assertEqual(len(set(sizes)),1)


if __name__=="__main__":
    unittest.main()
````

## `tests/test_parts.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/tests/test_parts.py`  
SHA256: `22b10eada72e5968c022604a8d86e1b7428dbb60abe75abdb085a0e927eeb74d`

````python
import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import Book,canonical
from plm_l1_v06.lexicon import tokenize,GOALS
from plm_l1_v06.features import observations,role_context,shape
from plm_l1_v06.projection import Space,dependency_leaves,fit_memory
from plm_l1_v06.training import fit
from plm_l1_v06.runtime import Model
from evaluation_support import data,train_for,FOLDS,heldout,text_goal,interpret,INVALID,OldSS,PartialTable,OldTable,opaque,normalize_markers
from measurements import bad_packets


class InheritedPartsTests(unittest.TestCase):
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
        self.assertEqual(list(inspect.signature(fit).parameters),["pairs","lexicon","seed","dimension","partial","learning","memory_mode"])

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
            for a,b in zip(model.memories[name].blocks,self.model.memories[name].blocks):
                self.assertEqual(a.blob,b.blob)

    def test_invalid_fit_settings(self):
        for kwargs in ({"partial":1},{"learning":0},{"dimension":129},{"seed":""}):
            with self.assertRaises(ValueError):
                fit(train_for(FOLDS[0]),self.lex,**kwargs)

    def test_no_hidden_japanese_grammar(self):
        from plm_l1_v06 import training,reader,runtime,features,projection
        for module in (training,reader,runtime,features,projection):
            code=inspect.getsource(module)
            for text in ("太郎","花子","もし","なかった",'"が"','"を"',"from evaluation_support","import plm_l1_v03","import plm_l1_v02"):
                self.assertNotIn(text,code)


if __name__=="__main__":
    unittest.main()
````

## `verify_release.py`

原本: `PLM-L1-v0.7/vendor/PLM-L1-v0.6/verify_release.py`  
SHA256: `7ad5a2385031c37a278bcbd6d53cd19b206c87262aacdd3d50338dd566b3d487`

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
from evaluation_support import ROOT, V05, V04, V03, V02, train_for, data, interpret, text_goal
from plm_l1_v06.algebra import digest
from plm_l1_v06.runtime import Model


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
        from plm_l1_v06.training import fit
        model = fit(train_for(protocol["folds"][0]), data("lexicon"), seed=protocol["development_seeds"][0])
        freeze, claimed, checks = "preflight_not_frozen", None, []
    else:
        freeze = verify_freeze()
        result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
        claimed = result.pop("result_digest")
        if digest(result) != claimed or result["freeze_hash"] != freeze:
            raise ValueError("evaluation integrity failure")
        checks = judge(result, protocol)
        if checks != result["checks"] or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        model = Model.load(ROOT / "results" / "model")
        first = result["standard"][0]["methods"]["split_proof"]
        if first["fingerprint"] != model.fingerprint:
            raise ValueError("saved model differs from evaluation")
    test_counts = {}
    for label, cwd in (("NEW_TESTS", ROOT), ("V05_TESTS", V05), ("V04_TESTS", V04), ("V03_TESTS", V03), ("V02_TESTS", V02), ("V01_TESTS", V02 / "vendor" / "PLM-L1-v0.1")):
        _, log = run(["-m", "unittest", "discover", "-s", "tests", "-v"], cwd, output, label)
        test_counts[label] = int(re.search(r"Ran (\d+) tests", log).group(1))

    # Same 432 training pairs and initial lexicon, no old packages or evaluators.
    training_only = output / "pair-training-only"
    copy_package(ROOT / "plm_l1_v06", training_only / "plm_l1_v06")
    shutil.copyfile(ROOT / "data" / "folds" / protocol["folds"][0] / "train.json", training_only / "train.json")
    shutil.copyfile(ROOT / "data" / "lexicon.json", training_only / "lexicon.json")
    assertion = "from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert all(importlib.util.find_spec(n) is None for n in ('plm_l1','plm_l1_v02','plm_l1_v03','plm_l1_v04','plm_l1_v05','evaluation_support')); assert not Path('evaluation.json').exists(); print('pair learner: no legacy model, teacher or evaluation corpus')"
    run(["-c", assertion], training_only, output, "PAIR_TRAIN_BOUNDARY")
    stdout, _ = run(["-m", "plm_l1_v06", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", model.meta["seed"], "--dimension", str(model.meta["dimension"]), "--out", "model"], training_only, output, "PAIR_TRAIN")
    if json.loads(stdout)["fingerprint"] != model.fingerprint:
        raise ValueError("isolated training differs")

    # Generation executable has neither reader.py nor training.py. Shared
    # numerical memories and feature/codec helpers remain: this is not proof
    # of absent reader-related knowledge or of all-symbolic-code removal.
    generation_only = output / "generation-only"
    copy_package(ROOT / "plm_l1_v06", generation_only / "plm_l1_v06", {"reader.py", "training.py"})
    shutil.copytree(training_only / "model", generation_only / "model")
    assertion = "from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('plm_l1_v06.reader','plm_l1_v06.training','plm_l1_v05','plm_l1_v04','plm_l1_v03','plm_l1_v02','plm_l1','evaluation_support')); assert not Path('train.json').exists(); print('generation: no reader/training entrypoint, legacy package or corpus; shared weights remain')"
    run(["-c", assertion], generation_only, output, "GENERATION_BOUNDARY")
    demos = []
    texts = ("花子を太郎が助けなかった。", "もし花子を太郎が助けなかったら。", "太郎を花子が助けなかった。", "太郎が花子を助けた。")
    for i, text in enumerate(texts):
        packet_name = f"meaning-{i}.json"
        run(["-m", "plm_l1_v06", "read", "--model", "model", "--text", text, "--out", packet_name], training_only, output, f"READ_{i}")
        packet = json.loads((training_only / packet_name).read_text(encoding="utf-8"))
        if set(packet) != {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}:
            raise ValueError("non-numerical payload leaked")
        shutil.copyfile(training_only / packet_name, generation_only / packet_name)
        stdout, _ = run(["-m", "plm_l1_v06", "generate", "--model", "model", "--packet", packet_name, "--goal", "object"], generation_only, output, f"GENERATE_{i}")
        out = json.loads(stdout)
        if out["status"] != "generated" or interpret(out["text"]) != interpret(text) or text_goal(out["text"]) != "object":
            raise ValueError("isolated generation changed meaning or goal")
        demos.append({"input_for_verifier_only": text, "output": out["text"], "meaning_and_goal_exact": True})
    # No feature selection/tree induction is invoked during inference.
    assertion = "import json; from unittest.mock import patch; from plm_l1_v06.runtime import Model; m=Model.load('model'); p=json.load(open('meaning-0.json',encoding='utf-8')); guard=patch('plm_l1_v06.banked.dependency_leaves',side_effect=AssertionError('runtime retraining')); guard.start(); assert m.generate(p,'object')['status']=='generated'; print('no runtime dependency learner call')"
    run(["-c", assertion], generation_only, output, "NO_RUNTIME_FEATURE_LEARNING")
    run(["-m", "plm_l1_v06", "read", "--model", "model", "--text", "未知が花子を助けた。", "--out", "must-not-exist.json"], training_only, output, "ABSTAIN", expected=2)
    if (training_only / "must-not-exist.json").exists():
        raise ValueError("abstention emitted packet")

    # Exercise the repaired low-dimensional contract through the ordinary CLI
    # in a directory without old code, not only in-process test doubles.
    run(["-m", "plm_l1_v06", "train", "--pairs", "train.json", "--lexicon", "lexicon.json", "--seed", "parts-stress-0", "--dimension", "128", "--memory-mode", "single", "--out", "low-model"], training_only, output, "LOW_DIMENSION_TRAIN")
    low_cases = []
    for i, text in enumerate(("花子が健太を褒めた。", "健太を花子が褒めた。")):
        filename = f"low-must-not-exist-{i}.json"
        stdout, _ = run(["-m", "plm_l1_v06", "read", "--model", "low-model", "--text", text, "--out", filename], training_only, output, f"LOW_DIMENSION_ABSTAIN_{i}", expected=2)
        low = json.loads(stdout)
        if low["reason"] != "meaning_signal_unrecoverable" or (training_only / filename).exists():
            raise ValueError("low-dimensional read contract failed")
        low_cases.append({"input": text, "mode": "single_legacy_equations_regression", "status": low["status"], "reason": low["reason"], "packet_file_absent": True})

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
              "known_low_dimension_cli_regressions": low_cases,
              "boundary_limit": "Shared full numerical model and feature helpers remain in generation-only environment.",
              "isolated_roundtrips": demos, "release_manifest_checked": manifest_checked,
              "full_numeric_rerun_in_this_command": False, "python": sys.version}
    (output / "VERIFICATION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

