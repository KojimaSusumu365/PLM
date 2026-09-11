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
