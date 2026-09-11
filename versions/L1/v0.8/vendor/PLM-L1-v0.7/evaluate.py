"""Frozen event-signal evaluation, separate from unchanged association memory."""
import argparse
import hashlib
import json
from pathlib import Path
from plm_l1_v06.algebra import digest
from plm_l1_v06.training import fit as fit_component
from plm_l1_v07.runtime import EventModel
from evaluation_support import ROOT,data,CATEGORIES,interpret,text_goal
from measurements import assess,codec_probe,noise_probe,count_rows,STAGES


def source_files():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py",".md",".txt")]
    for name in ("plm_l1_v07","plm_l1_v06","tests","evaluation","data","vendor"):
        files += [p for p in (ROOT/name).rglob("*") if p.is_file()]
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix!=".pyc")


def verify_freeze():
    manifest=json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    if actual!=manifest["files"]:
        raise ValueError("frozen source changed")
    return digest(manifest)


def judge(result,p):
    checks=[]
    def add(name,passed,**context):
        checks.append({"name":name,"passed":bool(passed),**context})
    expected={(s,m) for s in p["evaluation_seeds"] for m in p["standard_modes"]}
    if len(result["standard"])!=len(expected) or {(r["seed"],r["mode"]) for r in result["standard"]}!=expected:
        raise ValueError("standard inventory differs")
    for r in result["standard"]:
        if count_rows(r["records"])!=r["counts"] or r["dimension"]!=p["dimension"]:
            raise ValueError("standard counts/dimension differ")
        ctx={"seed":r["seed"],"mode":r["mode"]}
        for stage,n in (("read",288),("generate",288),("roundtrip",1152)):
            c=r["counts"][stage]
            add(stage+"_coverage",c["requests"]==n and c["exact"]/n>=.98,**ctx)
        for category in CATEGORIES:
            counts=count_rows([x for x in r["records"] if x["category"]==category])
            if counts!=r["categories"][category]:
                raise ValueError("category counts differ")
            for stage in STAGES:
                add("category_exact",counts[stage]["exact"]==counts[stage]["requests"]>0,category=category,stage=stage,**ctx)
        add("no_accepted_wrong_or_unrecoverable",all(c["wrong"]==0 for c in r["counts"].values()) and r["read_signal_unrecoverable"]==0,**ctx)
        add("invalid_documents_rejected",all(x["status"]=="abstain" for x in r["invalid_texts"]) and len(r["invalid_texts"])==14,**ctx)
        add("invalid_packets_rejected",all(x["status"]=="abstain" for x in r["invalid_packets"]) and len(r["invalid_packets"])==14,**ctx)
    expected={(s,d,m) for s in p["evaluation_seeds"] for d in p["codec_dimensions"] for m in p["codec_modes"]}
    if len(result["codec"])!=len(expected) or {(r["seed"],r["dimension"],r["mode"]) for r in result["codec"]}!=expected:
        raise ValueError("codec inventory differs")
    for r in result["codec"]:
        if count_rows(r["records"],("codec",))["codec"]!=r["counts"] or r["counts"]["requests"]!=72:
            raise ValueError("codec counts differ")
        add("equal_numeric_payload_budget",r["numeric_payload_bytes"]==16*r["dimension"],seed=r["seed"],dimension=r["dimension"],mode=r["mode"])
        distinct=[x for x in r["records"] if x["distinct_events"]]
        add("event_order_binding_control",len(distinct)==64 and all(x["swapped_signal_equal"]==(r["mode"]=="unbound") for x in distinct),seed=r["seed"],dimension=r["dimension"],mode=r["mode"])
    expected={(s,d,n) for s in p["noise_seeds"] for d in p["noise_dimensions"] for n in p["noise_levels"]}
    if len(result["noise"])!=len(expected) or {(r["seed"],r["dimension"],r["level"]) for r in result["noise"]}!=expected:
        raise ValueError("noise inventory differs")
    for r in result["noise"]:
        if count_rows(r["records"],("noise",))["noise"]!=r["counts"]:
            raise ValueError("noise counts differ")
        if r["dimension"]==8192 and r["level"]==0:
            add("zero_noise_high_dimension",r["counts"]["exact"]==r["counts"]["requests"]==72,seed=r["seed"])
    add("single_event_regression",result["component_regression"]["read_exact"]==192 and result["component_regression"]["generation_exact"]==384)
    add("no_learning_not_success",all(c["accepted"]==0 for c in result["no_learning"]["counts"].values()))
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
    p=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    split="development" if args.development else "evaluation"
    seeds=p["development_seeds"] if args.development else p["evaluation_seeds"]
    component=fit_component(data("folds/"+p["component_fold"]+"/train"),data("lexicon"),seed=p["component_seed"],dimension=p["component_dimension"])
    standard=[]
    for seed in seeds:
        for mode in p["standard_modes"]:
            model=EventModel(component,dimension=p["dimension"],seed=seed,mode=mode)
            r=assess(model,split); r.update(seed=seed,mode=mode,dimension=p["dimension"])
            standard.append(r)
            if len(standard)==1:
                model.save(output/"model")
            print(json.dumps({"standard":mode,"seed":seed,"counts":r["counts"]}),flush=True)
    codecs=[]
    for seed in seeds:
        for dimension in p["codec_dimensions"]:
            for mode in p["codec_modes"]:
                r=codec_probe(EventModel(component,dimension=dimension,seed=seed,mode=mode),split)
                r.update(seed=seed,mode=mode,dimension=dimension); codecs.append(r)
            print(json.dumps({"codec_dimension":dimension,"seed":seed}),flush=True)
    noise=[]
    noise_seeds=p["development_seeds"] if args.development else p["noise_seeds"]
    for seed in noise_seeds:
        for dimension in p["noise_dimensions"]:
            model=EventModel(component,dimension=dimension,seed=seed)
            for level in p["noise_levels"]:
                r=noise_probe(model,split,level,seed+"/noise"); r.update(seed=seed,dimension=dimension,level=level); noise.append(r)
            print(json.dumps({"noise_dimension":dimension,"seed":seed}),flush=True)
    regression={"read_exact":0,"generation_exact":0}
    for row in data(split):
        r=component.read(row["text"])
        regression["read_exact"]+=int(r["status"]=="read" and component.recover(r["packet"])["meaning"]==row["meaning"])
        for goal in ("subject","object"):
            out=component.generate(component.encode(row["meaning"]),goal)
            regression["generation_exact"]+=int(out["status"]=="generated" and interpret(out["text"])==row["meaning"] and text_goal(out["text"])==goal)
    disabled=fit_component(data("folds/"+p["component_fold"]+"/train"),data("lexicon"),seed=p["component_seed"],learning=False)
    result={"schema":"plm-l1-v07-results-v1","freeze_hash":freeze,"component_fingerprint":component.fingerprint,
            "standard":standard,"codec":codecs,"noise":noise,"component_regression":regression,"no_learning":assess(EventModel(disabled),split)}
    result["checks"]=[] if args.development else judge(result,p)
    result["passed"]=bool(result["checks"]) and all(c["passed"] for c in result["checks"])
    result["result_digest"]=digest(result)
    (output/"EVALUATION.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    from report import write_report
    write_report(output,result)
    print("RESULT_DIGEST "+result["result_digest"],flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
