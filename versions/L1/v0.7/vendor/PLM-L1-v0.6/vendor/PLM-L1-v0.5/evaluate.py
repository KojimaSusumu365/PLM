"""Frozen comparison of acceptance contracts, capacity and signal perturbation."""
import argparse
import hashlib
import json
from pathlib import Path
from plm_l1_v05.algebra import digest
from plm_l1_v05.training import fit
from evaluation_support import ROOT, data, train_for, paired_models
from measurements import BUCKETS, assess, accepted_subset, bad_packets, channel, memory_load


def source_files():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py",".md",".txt")]
    for name in ("plm_l1_v05","tests","evaluation","data","vendor"):
        files += [p for p in (ROOT/name).rglob("*") if p.is_file()]
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix!=".pyc")


def verify_freeze():
    manifest=json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    if actual!=manifest["files"]:
        raise ValueError("frozen source changed")
    return digest(manifest)


def pair(pairs,seed,dimension,split,fold):
    new,old = paired_models(pairs,seed,dimension)
    a,b = assess(new,split,fold),assess(old,split,fold)
    return {"fold":fold,"seed":seed,"dimension":dimension,"weights_equal":True,"acceptance_subset":accepted_subset(a,b),"checked":a,"v04":b},new


def known_regressions(protocol):
    new,old = paired_models(train_for(protocol["folds"][0]),protocol["legacy_fixture_seed"],protocol["legacy_fixture_dimension"])
    records=[]
    for text in protocol["legacy_fixture_texts"]:
        a,b = new.read(text),old.read(text)
        recovered = old.recover(b["packet"]) if b["status"]=="read" else {"status":"not_requested"}
        records.append({"input":text,"old_status":b["status"],"old_recovery":recovered,"checked_status":a["status"],"checked_reason":a.get("reason"),"checked_recovery_reason":a.get("recovery_reason"),
                        "checked_packet_absent":a.get("packet") is None,"weights_equal":True,"new_fingerprint":new.fingerprint,"old_fingerprint":old.fingerprint})
    return records


def judge(result,protocol):
    checks=[]
    def add(name,passed,**context):
        checks.append({"name":name,"passed":bool(passed),**context})
    expected={(f,s) for f in protocol["folds"] for s in protocol["evaluation_seeds"]}
    if len(result["standard"])!=len(expected) or {(r["fold"],r["seed"]) for r in result["standard"]}!=expected:
        raise ValueError("standard evaluation inventory differs")
    inventories = (
        ("dimension", ("seed","dimension"), {(s,d) for s in protocol["dimension_seeds"] for d in protocol["dimension_values"]}),
        ("channel", ("seed","dimension","noise_level","condition"), {(s,d,n,c) for s in protocol["channel_seeds"] for d in protocol["channel_dimensions"] for n in protocol["noise_levels"] for c in ("checked","v04")}),
        ("memory", ("seed","dimension","load"), {(s,d,n) for s in protocol["memory_seeds"] for d in protocol["memory_dimensions"] for n in protocol["memory_loads"]}),
    )
    for name,fields,expected_rows in inventories:
        rows=result[name]
        if len(rows)!=len(expected_rows) or {tuple(r[f] for f in fields) for r in rows}!=expected_rows:
            raise ValueError(name+" evaluation inventory differs")
    if [r["input"] for r in result["known_regressions"]]!=protocol["legacy_fixture_texts"]:
        raise ValueError("known regression inventory differs")
    for r in result["standard"]:
        a,b = r["checked"]["counts"],r["v04"]["counts"]
        if r["dimension"]!=protocol["dimension"] or any(r[k]["training_pairs"]!=432 for k in ("checked","v04")):
            raise ValueError("standard training budget differs")
        ctx={"fold":r["fold"],"seed":r["seed"]}
        for key in BUCKETS:
            add(key+"_coverage",a[key+"_exact"]/a[key+"_requests"]>=.98,**ctx)
            add(key+"_preserved",a[key+"_exact"]==b[key+"_exact"] and a[key+"_requests"]==b[key+"_requests"],**ctx)
        add("no_wrong",all(a[k+"_wrong"]==0 for k in BUCKETS),**ctx)
        add("invalid_boundaries",a["invalid_text_accepted"]+a["invalid_packet_generated"]==0,**ctx)
        add("read_signal_consistent",a["read_signal_unrecoverable"]==0,**ctx)
        add("unchanged_weights_and_subset",r["weights_equal"] and r["acceptance_subset"],**ctx)
    for r in result["known_regressions"]:
        add("known_failure_now_abstains",r["old_status"]=="read" and r["old_recovery"]["status"]=="abstain" and r["checked_status"]=="abstain" and r["checked_reason"]=="meaning_signal_unrecoverable" and r["checked_packet_absent"],input=r["input"])
    for r in result["dimension"]:
        add("dimension_contract_and_subset",r["checked"]["counts"]["read_signal_unrecoverable"]==0 and r["acceptance_subset"] and r["weights_equal"],dimension=r["dimension"],seed=r["seed"])
    r = result["full_training"]
    c = r["checked"]["counts"]
    add("full_training_regression",all(c[k+"_exact"]==c[k+"_requests"] for k in BUCKETS) and c["read_signal_unrecoverable"]+c["invalid_text_accepted"]+c["invalid_packet_generated"]==0 and r["weights_equal"])
    for r in result["channel"]:
        if r["condition"]=="checked" and r["noise_level"]==0:
            c=r["counts"]
            add("zero_noise_read_recoverability",c["recover_accepted"]==c["source_read_accepted"]==c["recover_requests"],dimension=r["dimension"],seed=r["seed"])
    add("ordinary_memory_control",all(r["table_reference"]["known_exact"]==r["load"] and r["table_reference"]["missing_correct_rejection"]==64 for r in result["memory"]))
    add("no_learning_not_success",all(result["no_learning"]["counts"][k+"_accepted"]==0 for k in BUCKETS))
    if len(checks)!=283:
        raise ValueError("expected 283 checks, got "+str(len(checks)))
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
    standard=[]
    for fold in protocol["folds"]:
        for seed in seeds:
            r,model=pair(train_for(fold),seed,protocol["dimension"],split,fold)
            standard.append(r)
            print(json.dumps({"standard":fold,"seed":seed,"counts":r["checked"]["counts"]}),flush=True)
            if len(standard)==1:
                model.save(output/"model")
    dimensions=[]
    stress_seeds=protocol["development_seeds"] if args.development else protocol["dimension_seeds"]
    for seed in stress_seeds:
        for dimension in protocol["dimension_values"]:
            r,_=pair(train_for(protocol["folds"][0]),seed,dimension,split,protocol["folds"][0])
            dimensions.append(r)
            print(json.dumps({"dimension":dimension,"seed":seed,"counts":r["checked"]["counts"]}),flush=True)
    channels=[]
    channel_seeds=protocol["development_seeds"] if args.development else protocol["channel_seeds"]
    for seed in channel_seeds:
        for dimension in protocol["channel_dimensions"]:
            models=paired_models(train_for(protocol["folds"][0]),seed,dimension)
            for level in protocol["noise_levels"]:
                for condition,model in zip(("checked","v04"),models):
                    r=channel(model,split,level,seed+"/noise")
                    r.update(seed=seed,dimension=dimension,noise_level=level,condition=condition)
                    channels.append(r)
            print(json.dumps({"channel_dimension":dimension,"seed":seed}),flush=True)
    memory=[]
    memory_seeds=protocol["development_seeds"] if args.development else protocol["memory_seeds"]
    for seed in memory_seeds:
        for dimension in protocol["memory_dimensions"]:
            for load in protocol["memory_loads"]:
                memory.append(memory_load(dimension,load,seed))
            print(json.dumps({"memory_dimension":dimension,"seed":seed}),flush=True)
    full,_=pair(data("train"),"checked-full-regression-0",8192,split,protocol["folds"][0])
    no_learning=assess(fit(train_for(protocol["folds"][0]),data("lexicon"),learning=False),split,protocol["folds"][0])
    result={"schema":"plm-l1-v05-results-v1","freeze_hash":freeze,"standard":standard,"dimension":dimensions,"channel":channels,"memory":memory,
            "full_training":full,"no_learning":no_learning,"known_regressions":known_regressions(protocol)}
    result["checks"]=[] if args.development else judge(result,protocol)
    result["passed"]=bool(result["checks"]) and all(c["passed"] for c in result["checks"])
    result["result_digest"]=digest(result)
    (output/"EVALUATION.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    from report import write_report
    write_report(output,result)
    print("RESULT_DIGEST "+result["result_digest"],flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
