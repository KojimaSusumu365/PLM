# PLM-L1-v0.7 全コード（当該版直下・vendor重複除外）

原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。

## `build_data.py`

原本: `PLM-L1-v0.7/build_data.py`  
SHA256: `1ec7fe8b93aaf97cc38c81475c1557e17587dad5154c71b7dab71a5d65c7db94`

````python
"""Compose new two-event data with an evaluator-only synthetic grammar."""
import hashlib
import json
from plm_l1_v06.algebra import canonical
from evaluation_support import ROOT,data,render,CATEGORIES,GOAL_PAIRS,parse_document


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def build(split):
    lex=data("lexicon")
    names=lex["slot_candidates"]["subject"]
    predicates=lex["slot_candidates"]["predicate"]
    triples=sorted({tuple(r["meaning"][k] for k in ("subject","object","predicate")) for r in data(split)},key=lambda t:hashlib.sha256(canonical(["event-corpus-v1",t]).encode()).hexdigest())[:8]
    rows=[]
    for index,(subject,obj,predicate) in enumerate(triples):
        first={"subject":subject,"object":obj,"predicate":predicate,"polarity":"polarity:"+("negative" if index%2 else "positive"),"modality":"modality:"+("hypothetical" if (index//2)%2 else "asserted")}
        others=[n for n in names if n not in (subject,obj)]
        alternate=predicates[(predicates.index(predicate)+1)%len(predicates)]
        variants={
            "separate_participants":dict(first,subject=others[0],object=others[1],predicate=alternate),
            "shared_subject":dict(first,object=others[0],predicate=alternate),
            "shared_object":dict(first,subject=others[0],predicate=alternate),
            "role_chain":dict(first,subject=obj,object=others[0],predicate=alternate),
            "role_reversal":dict(first,subject=obj,object=subject),
            "polarity_scope":dict(first,polarity="polarity:positive" if index%2 else "polarity:negative"),
            "modality_scope":dict(first,modality="modality:asserted" if (index//2)%2 else "modality:hypothetical"),
            "identical_mentions":dict(first),
            "predicate_scope":dict(first,predicate=alternate),
        }
        for category in CATEGORIES:
            meaning={"events":[first,variants[category]]}
            for goal_index,goals in enumerate(GOAL_PAIRS):
                text=render(first,goals[0])+render(variants[category],goals[1])
                assert parse_document(text)==meaning
                rows.append({"id":f"{split}-{index}-{category}-{goal_index}","category":category,"text":text,"meaning":meaning,"input_goals":goals})
    assert len(rows)==288 and len({r["text"] for r in rows})==288
    return rows


def main():
    development,evaluation=build("development"),build("evaluation")
    a={canonical(r["meaning"]) for r in development}
    b={canonical(r["meaning"]) for r in evaluation}
    assert not a&b
    write(ROOT/"data"/"events_development.json",development)
    write(ROOT/"data"/"events_evaluation.json",evaluation)
    train=data("folds/object_negative/train")
    train_triples={tuple(r["meaning"][k] for k in ("subject","object","predicate")) for r in train}
    audit={"schema":"plm-two-event-corpus-audit-v1","component_training_pairs":len(train),"two_event_training_pairs":0,
           "development_documents":len(development),"evaluation_documents":len(evaluation),"development_meanings":len(a),"evaluation_meanings":len(b),
           "ordered_pair_overlap":len(a&b),"categories":list(CATEGORIES),"input_goal_pairs":GOAL_PAIRS,
           "evaluation_first_event_lexical_triple_absent_from_training":all(tuple(r["meaning"]["events"][0][k] for k in ("subject","object","predicate")) not in train_triples for r in evaluation),
           "scope":"New ordered pairs and new paired texts, built from old controlled grammar/vocabulary and reused one-event split. Not an independently collected natural-language corpus. Sentence segmentation/event positions designed, not learned."}
    write(ROOT/"data"/"EVENT_SPLIT_AUDIT.json",audit)
    print(json.dumps(audit,ensure_ascii=False))


if __name__=="__main__":
    main()
````

## `evaluate.py`

原本: `PLM-L1-v0.7/evaluate.py`  
SHA256: `d6277e105111f7fe4efe0bcd7bfde8c0173132e39280e289544a931276db9a97`

````python
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
````

## `evaluation_support.py`

原本: `PLM-L1-v0.7/evaluation_support.py`  
SHA256: `f5d916ca4a0baaa6aaa068dab29a0da9b7eb72f9ea98aa485d2bd82ef9e9d41a`

````python
"""Evaluator-only independent grammar and old regression interfaces."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
V06=ROOT/"vendor"/"PLM-L1-v0.6"
V05=V06/"vendor"/"PLM-L1-v0.5"
V04=V05/"vendor"/"PLM-L1-v0.4"
V03=V04/"vendor"/"PLM-L1-v0.3"
V02=V03/"vendor"/"PLM-L1-v0.2"
V01=V02/"vendor"/"PLM-L1-v0.1"
for path in (V06,V05,V04,V03,V02,V01):
    if str(path) not in sys.path:
        sys.path.append(str(path))
spec=importlib.util.spec_from_file_location("event_legacy_support",V06/"evaluation_support.py")
legacy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
interpret,text_goal,heldout=legacy.interpret,legacy.text_goal,legacy.heldout
from plm_l1.teacher import surface,VERBS

GOAL_PAIRS=[[a,b] for a in ("subject","object") for b in ("subject","object")]
CATEGORIES=("separate_participants","shared_subject","shared_object","role_chain","role_reversal","polarity_scope","modality_scope","identical_mentions","predicate_scope")


def data(name):
    return json.loads((ROOT/"data"/(name+".json")).read_text(encoding="utf-8"))


def render(event,goal):
    stem=dict(("predicate:"+pred,stem) for stem,pred in VERBS)[event["predicate"]]
    return surface(event["subject"].split(":",1)[1],event["object"].split(":",1)[1],stem,event["polarity"].split(":",1)[1],event["modality"].split(":",1)[1],goal+"_first")


def parse_document(text):
    if type(text) is not str or text.count("。")!=2 or not text.endswith("。"):
        return None
    events=[interpret(part+"。") for part in text.split("。")[:2]]
    return {"events":events} if all(e is not None for e in events) else None


def document_goals(text):
    return [text_goal(part+"。") for part in text.split("。")[:2]] if parse_document(text) is not None else None
````

## `measurements.py`

原本: `PLM-L1-v0.7/measurements.py`  
SHA256: `46a455bbdad8a0cf6a91c3bc586210cf766a35204b274925d6dbdc6483cd843f`

````python
"""Independent ordered-event scoring and numerical controls."""
import copy
import hashlib
import numpy as np
from plm_l1_v06.algebra import canonical
from plm_l1_v07.runtime import EventModel
from evaluation_support import data,GOAL_PAIRS,CATEGORIES,parse_document,document_goals

STAGES=("read","generate","roundtrip")
INVALID_TEXTS=("", "太郎が花子を助けた。", "太郎が花子を助けた。花子が太郎を助けた。健太が美咲を褒めた。",
               "太郎が花子を助けた。。", "。花子が太郎を助けた。", "太郎が花子を助けた。花子が太郎を助けた",
               "太郎が花子を助けた。彼が太郎を助けた。", "太郎が花子を助けた。それから花子が太郎を助けた。",
               "未知が花子を助けた。花子が太郎を助けた。", "太郎が花子を助けた。花子が未知を助けた。",
               "太郎が花子を助けた。花子を助けた。", "太郎が花子を助けた。もし花子が太郎を助けた。",
               "太郎は花子を助けた。花子が太郎を助けた。", "太郎が花子を助けた。花子が太郎を助けた。。")


def count_rows(records,stages=STAGES):
    return {stage:{k:sum((row["stage"]==stage) and condition(row) for row in records) for k,condition in {
        "requests":lambda r:True,"accepted":lambda r:r["accepted"],"exact":lambda r:r["exact"],
        "wrong":lambda r:r["accepted"] and not r["exact"],"abstained":lambda r:not r["accepted"]}.items()} for stage in stages}


def confusion(actual,expected):
    if actual is None:
        return {"event_swapped":False,"cross_event_slots":0,"slot_errors":0}
    a,b=actual["events"],expected["events"]
    return {"event_swapped":a==list(reversed(b)) and b[0]!=b[1],
            "slot_errors":sum(a[i][k]!=b[i][k] for i in range(2) for k in b[i]),
            "cross_event_slots":sum(a[i][k]!=b[i][k] and a[i][k]==b[1-i][k] for i in range(2) for k in b[i])}


def unique_rows(split):
    rows={canonical(r["meaning"]):r for r in data("events_"+split)}
    return [rows[k] for k in sorted(rows)]


def bad_packets(model,meaning):
    p=model.encode(meaning); n=p["dimension"]
    result=[None,[],dict(p,events=meaning["events"]),dict(p,text="source"),dict(p,model_fingerprint="bad"),
            dict(p,dimension=True),dict(p,eligible_for_inference=True),dict(p,real=[0.]*n,imag=[0.]*n),dict(p,real=p["real"][:-1])]
    for value in (float("nan"),float("inf"),True,"1",1e100):
        q=copy.deepcopy(p); q["real"][0]=value; result.append(q)
    return result


def assess(model,split):
    records=[]
    unrecoverable=0
    for row in data("events_"+split):
        out=model.read(row["text"])
        accepted=out["status"]=="read"
        recovered=model.recover(out["packet"]) if accepted else {"meaning":None,"status":"not_requested"}
        actual=recovered.get("meaning")
        unrecoverable+=int(accepted and recovered["status"]!="recovered")
        signal=None
        if accepted:
            v=np.array(out["packet"]["real"])+1j*np.array(out["packet"]["imag"])
            signal=hashlib.sha256(v.astype("<c16").tobytes()).hexdigest()
        records.append({"stage":"read","id":row["id"],"category":row["category"],"input":row["text"],"expected":row["meaning"],"actual":actual,
                        "accepted":accepted,"exact":accepted and actual==row["meaning"],"reason":out.get("reason"),"signal_digest":signal,**confusion(actual,row["meaning"])})
        for goals in GOAL_PAIRS:
            generated=model.generate(out["packet"],goals) if accepted else {"status":"abstain","reason":"reader_abstained"}
            records.append(score_generation("roundtrip",row,goals,generated))
    for row in unique_rows(split):
        p=model.encode(row["meaning"])
        for goals in GOAL_PAIRS:
            records.append(score_generation("generate",row,goals,model.generate(p,goals)))
    invalid=[{"input":t,"status":model.read(t)["status"]} for t in INVALID_TEXTS]
    malformed=[{"index":i,"status":model.generate(p)["status"]} for i,p in enumerate(bad_packets(model,unique_rows(split)[0]["meaning"]))]
    return {"counts":count_rows(records),"categories":{c:count_rows([r for r in records if r["category"]==c]) for c in CATEGORIES},
            "records":records,"invalid_texts":invalid,"invalid_packets":malformed,"read_signal_unrecoverable":unrecoverable,"fingerprint":model.fingerprint}


def score_generation(stage,row,goals,out):
    accepted=out["status"]=="generated"
    actual=parse_document(out.get("text"))
    return {"stage":stage,"id":row["id"],"category":row["category"],"expected":row["meaning"],"actual":actual,"goals":goals,"output":out.get("text"),
            "accepted":accepted,"exact":accepted and actual==row["meaning"] and document_goals(out["text"])==goals,"reason":out.get("reason"),**confusion(actual,row["meaning"])}


def codec_probe(model,split):
    records=[]
    for row in unique_rows(split):
        p=model.encode(row["meaning"])
        r=model.recover(p)
        actual=r.get("meaning")
        opposite={"events":list(reversed(row["meaning"]["events"]))}
        a,b=model.codec.encode(row["meaning"]),model.codec.encode(opposite)
        records.append({"stage":"codec","category":row["category"],"expected":row["meaning"],"actual":actual,"accepted":r["status"]=="recovered",
                        "exact":actual==row["meaning"],"reason":r.get("reason"),"distinct_events":opposite!=row["meaning"],"swapped_signal_equal":bool(np.array_equal(a,b)),
                        "swapped_relative_distance":round(float(np.linalg.norm(a-b)/np.linalg.norm(a)),8),**confusion(actual,row["meaning"])})
    return {"counts":count_rows(records,("codec",))["codec"],"records":records,"numeric_payload_bytes":16*model.codec.dimension,"fingerprint":model.fingerprint}


def noise_probe(model,split,level,seed):
    records=[]
    for row in unique_rows(split):
        p=model.encode(row["meaning"])
        v=np.array(p["real"])+1j*np.array(p["imag"])
        key=int.from_bytes(hashlib.sha256(canonical([seed,row["meaning"]]).encode()).digest()[:16],"little")
        rng=np.random.Generator(np.random.PCG64(key))
        z=rng.standard_normal(len(v))+1j*rng.standard_normal(len(v))
        z*=level*np.linalg.norm(v)/np.linalg.norm(z)
        p["real"],p["imag"]=(v+z).real.tolist(),(v+z).imag.tolist()
        r=model.recover(p); actual=r.get("meaning")
        records.append({"stage":"noise","expected":row["meaning"],"actual":actual,"accepted":r["status"]=="recovered","exact":actual==row["meaning"],"reason":r.get("reason"),**confusion(actual,row["meaning"])})
    return {"counts":count_rows(records,("noise",))["noise"],"records":records,"fingerprint":model.fingerprint}
````

## `plm_l1_v06/__init__.py`

原本: `PLM-L1-v0.7/plm_l1_v06/__init__.py`  
SHA256: `8f05c473108f28e82f66110c2c81924843fd68b7c4b9de5dfd6e67c695fb0443`

````python
"""PLM-L1 0.6.0: fixed-budget banked phase memory with pair evidence."""
__version__ = "0.6.0"
````

## `plm_l1_v06/__main__.py`

原本: `PLM-L1-v0.7/plm_l1_v06/__main__.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/algebra.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/banked.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/features.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/lexicon.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/projection.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/reader.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/runtime.py`  
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

原本: `PLM-L1-v0.7/plm_l1_v06/training.py`  
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

## `plm_l1_v07/__init__.py`

原本: `PLM-L1-v0.7/plm_l1_v07/__init__.py`  
SHA256: `b2005759a45030ed9c8fd399cfcf46192fc94512d6deb69835b1a78d48ed366d`

````python
"""Two explicitly delimited events in one SS/VSA phase signal."""
__version__ = "0.7.0"
````

## `plm_l1_v07/__main__.py`

原本: `PLM-L1-v0.7/plm_l1_v07/__main__.py`  
SHA256: `3d444ecff412a2872ecac9531063aa93c516b405632b4c333a182c47c3b95b76`

````python
import argparse
import json
from pathlib import Path
from .runtime import EventModel


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path,value):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def main():
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest="command",required=True)
    train=commands.add_parser("train")
    for name in ("pairs","lexicon","out"):
        train.add_argument("--"+name,required=True)
    train.add_argument("--component-seed",default="banked-evaluation-0")
    train.add_argument("--event-seed",default="events-development-0")
    train.add_argument("--dimension",type=int,default=8192)
    train.add_argument("--mode",choices=("bound","partitioned","unbound"),default="bound")
    for name in ("read","encode","recover","generate"):
        p=commands.add_parser(name)
        p.add_argument("--model",required=True)
        if name in ("read","encode"):
            p.add_argument("--text" if name=="read" else "--meaning",required=True)
            p.add_argument("--out",required=True)
        else:
            p.add_argument("--packet",required=True)
        if name=="generate":
            p.add_argument("--goals",nargs=2,choices=("subject","object"),default=["subject","subject"])
    args=parser.parse_args()
    try:
        if args.command=="train":
            from .training import fit
            model=fit(load(args.pairs),load(args.lexicon),component_seed=args.component_seed,event_seed=args.event_seed,dimension=args.dimension,mode=args.mode)
            model.save(args.out)
            result={"status":"trained","fingerprint":model.fingerprint,"component_fingerprint":model.component.fingerprint,"two_event_binding_learned":False}
        else:
            model=EventModel.load(args.model)
            if args.command=="read":
                result=model.read(args.text)
                if result["status"]=="read":
                    write(args.out,result.pop("packet"))
            elif args.command=="encode":
                write(args.out,model.encode(load(args.meaning)))
                result={"status":"encoded"}
            elif args.command=="recover":
                result=model.recover(load(args.packet))
            else:
                result=model.generate(load(args.packet),args.goals)
        print(json.dumps(result,ensure_ascii=False))
        return 2 if result["status"]=="abstain" else 0
    except (ValueError,TypeError,OSError,KeyError) as error:
        print(json.dumps({"status":"error","reason":str(error)},ensure_ascii=False))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
````

## `plm_l1_v07/codec.py`

原本: `PLM-L1-v0.7/plm_l1_v07/codec.py`  
SHA256: `7472941c641c5ece9ee08c4cc0ea088414dbbf5f6a1ba72f312693623b283865`

````python
"""Event binding, superposition and correlation; no text or training corpus."""
import math
import numpy as np
from plm_l1_v06.algebra import require
from plm_l1_v06.banked import FreshBook
from plm_l1_v06.lexicon import ROLES,validate_meaning

MODES=("bound","partitioned","unbound")


class EventCodec:
    def __init__(self,candidates,dimension=8192,seed="events-development-0",mode="bound"):
        require(type(dimension) is int and 128<=dimension<=16384 and dimension%128==0,"invalid_event_dimension")
        require(type(seed) is str and 0<len(seed)<=128,"invalid_event_seed")
        require(type(mode) is str and mode in MODES,"invalid_event_mode")
        self.candidates={r:tuple(candidates[r]) for r in ROLES}
        self.dimension,self.seed,self.mode=dimension,seed,mode
        self.width=dimension//2 if mode=="partitioned" else dimension
        self.scale=1. if mode=="partitioned" else 1/math.sqrt(2.)
        book=FreshBook(self.width,seed)
        presence=book.code("event_presence","present")
        self.bindings=[book.code("event_position",i) if mode=="bound" else np.ones(self.width,dtype=np.complex128) for i in range(2)]
        self.presence=[b*presence for b in self.bindings]
        self.codes=[{r:np.array([b*book.code("event_role",r)*book.code("event_value",v) for v in self.candidates[r]]) for r in ROLES} for b in self.bindings]

    def validate(self,meaning):
        require(type(meaning) is dict and set(meaning)=={"events"},"invalid_two_event_fields")
        require(type(meaning["events"]) is list and len(meaning["events"])==2,"exactly_two_events_required")
        for event in meaning["events"]:
            validate_meaning(event,self.candidates)

    def encode(self,meaning):
        self.validate(meaning)
        frames=[]
        for i,event in enumerate(meaning["events"]):
            frame=self.presence[i].copy()
            for role in ROLES:
                frame+=self.codes[i][role][self.candidates[role].index(event[role])]
            frames.append(frame)
        return np.concatenate(frames) if self.mode=="partitioned" else (frames[0]+frames[1])*self.scale

    def recover(self,vector):
        require(isinstance(vector,np.ndarray) and vector.shape==(self.dimension,) and np.isfinite(vector).all(),"invalid_event_vector")
        meaning={"events":[]}
        audits=[]
        for i in range(2):
            part=vector[i*self.width:(i+1)*self.width] if self.mode=="partitioned" else vector/self.scale
            presence=float(np.vdot(self.presence[i],part).real/self.width)
            require(presence>=.65,"event_presence_weak")
            event,audit={}, {"event_index":i,"presence":round(presence,8),"slots":{}}
            for role in ROLES:
                scores=(self.codes[i][role].conj()@part).real/self.width
                order=np.argsort(-scores,kind="stable")
                top=float(scores[order[0]])
                runner=max(0.,float(scores[order[1]]))
                require(top>=.65 and top-runner>=.25,"event_slot_ambiguous")
                event[role]=self.candidates[role][order[0]]
                audit["slots"][role]={"score":round(top,8),"margin":round(top-runner,8)}
            meaning["events"].append(event)
            audits.append(audit)
        clean=self.encode(meaning)
        residual=float(np.linalg.norm(vector-clean)/np.linalg.norm(clean))
        require(residual<=.20,"event_signal_residual_excessive")
        return {"meaning":meaning,"residual":round(residual,8),"audit":audits}
````

## `plm_l1_v07/reader.py`

原本: `PLM-L1-v0.7/plm_l1_v07/reader.py`  
SHA256: `83ebed311e9f073f30e12a21d376eea474da4281ffe992fd019e6092b43eac78`

````python
"""Explicit two-sentence boundary; event structure is designed, not learned."""
from plm_l1_v06.algebra import require
from plm_l1_v06.runtime import abstain


def read(model,text):
    try:
        require(type(text) is str and 0<len(text)<=514,"invalid_document_text")
        parts=text.strip().split(model.meta["terminator"])
        require(len(parts)==3 and parts[-1]=="" and all(p.strip() for p in parts[:2]),"exactly_two_terminated_sentences_required")
        events=[]
        for index,part in enumerate(parts[:2]):
            out=model.component.read(part.strip()+model.meta["terminator"])
            require(out["status"]=="read","event_read_failed:"+str(index)+":"+out.get("reason","unknown"))
            recovered=model.component.recover(out["packet"])
            require(recovered["status"]=="recovered","component_signal_unrecoverable")
            events.append(recovered["meaning"])
        candidate={"events":events}
        packet=model.encode(candidate)
        recovered=model.recover(packet)
        require(recovered["status"]=="recovered","two_event_signal_unrecoverable")
        require(recovered["meaning"]==candidate,"two_event_signal_mismatch")
        return {"status":"read","packet":packet,"event_count":2,"signal_verified":True,"eligible_for_inference":False}
    except (ValueError,TypeError) as error:
        return abstain(str(error))
````

## `plm_l1_v07/runtime.py`

原本: `PLM-L1-v0.7/plm_l1_v07/runtime.py`  
SHA256: `49fed354931001f6626507cf335c8ed3e1d6426ba92901ddb560a5fee16d338e`

````python
"""Numerical two-event contract and atomic generation. No reader/learner imports."""
import json
from pathlib import Path
import numpy as np
from plm_l1_v06.algebra import canonical,digest,require
from plm_l1_v06.runtime import Model as ComponentModel,abstain
from plm_l1_v06.lexicon import GOALS
from .codec import EventCodec

PACKET_FIELDS={"schema","model_fingerprint","dimension","real","imag","eligible_for_inference"}


class EventModel:
    def __init__(self,component,*,dimension=8192,seed="events-development-0",mode="bound"):
        require(isinstance(component,ComponentModel),"invalid_component_model")
        self.component=component
        self.codec=EventCodec(component.meta["slot_candidates"],dimension,seed,mode)
        self.meta={"schema":"plm-two-event-model-v1","component_fingerprint":component.fingerprint,
                   "dimension":dimension,"seed":seed,"mode":mode,"event_count":2,
                   "event_positions":"mention_order_only","terminator":"。","binding_learning":"designed_not_learned",
                   "read_acceptance":"recover_equals_both_candidates_v1","eligible_for_inference":False}
        self.fingerprint=digest(self.meta)

    def encode(self,meaning):
        v=self.codec.encode(meaning)
        return {"schema":"plm-two-event-signal-v1","model_fingerprint":self.fingerprint,"dimension":self.codec.dimension,
                "real":v.real.tolist(),"imag":v.imag.tolist(),"eligible_for_inference":False}

    def recover(self,packet):
        try:
            require(type(packet) is dict and set(packet)==PACKET_FIELDS,"unexpected_packet_fields")
            require(packet["schema"]=="plm-two-event-signal-v1" and packet["model_fingerprint"]==self.fingerprint,"packet_model_mismatch")
            require(type(packet["dimension"]) is int and packet["dimension"]==self.codec.dimension and packet["eligible_for_inference"] is False,"invalid_packet_contract")
            for field in ("real","imag"):
                require(type(packet[field]) is list and len(packet[field])==self.codec.dimension and all(type(v) in (int,float) for v in packet[field]),"invalid_signal_values")
            vector=np.array(packet["real"],dtype=float)+1j*np.array(packet["imag"],dtype=float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector))<=32.,"invalid_signal_values")
            return {"status":"recovered",**self.codec.recover(vector),"eligible_for_inference":False}
        except (ValueError,TypeError,OverflowError) as error:
            return abstain(str(error),meaning=None)

    def read(self,text):
        from .reader import read
        return read(self,text)

    def generate(self,packet,goals=("subject","subject")):
        try:
            require(type(goals) in (list,tuple) and len(goals)==2 and all(type(g) is str and g in GOALS for g in goals),"invalid_event_goals")
            recovered=self.recover(packet)
            require(recovered["status"]=="recovered",recovered.get("reason","event_recovery_failed"))
            texts=[]
            for index,event in enumerate(recovered["meaning"]["events"]):
                out=self.component.generate(self.component.encode(event),goals[index])
                require(out["status"]=="generated","event_generation_failed:"+str(index)+":"+out.get("reason","unknown"))
                texts.append(out["text"])
            return {"status":"generated","text":"".join(texts),"event_count":2,"eligible_for_inference":False}
        except (ValueError,TypeError) as error:
            return abstain(str(error))

    def save(self,directory):
        target=Path(directory)
        require(not (target/"model.json").exists() and not (target/"component").exists(),"output_exists")
        target.mkdir(parents=True,exist_ok=True)
        self.component.save(target/"component")
        with (target/"model.json").open("x",encoding="utf-8") as stream:
            stream.write(json.dumps({"metadata":self.meta,"fingerprint":self.fingerprint},ensure_ascii=False,indent=2)+"\n")

    @classmethod
    def load(cls,directory):
        target=Path(directory)
        info=json.loads((target/"model.json").read_text(encoding="utf-8"))
        require(type(info) is dict and set(info)=={"metadata","fingerprint"},"invalid_model_envelope")
        m=info["metadata"]
        model=cls(ComponentModel.load(target/"component"),dimension=m["dimension"],seed=m["seed"],mode=m["mode"])
        require(model.meta==m and model.fingerprint==info["fingerprint"],"model_hash_mismatch")
        return model
````

## `plm_l1_v07/training.py`

原本: `PLM-L1-v0.7/plm_l1_v07/training.py`  
SHA256: `a28011eef2e134fd03a97e588db87ef2e876089fbe1fafdb77137a500d4c9dd6`

````python
"""Relearn single-event components from pairs; two-event binding is not learned."""
from plm_l1_v06.training import fit as fit_component
from .runtime import EventModel


def fit(pairs,lexicon,*,component_seed="banked-evaluation-0",event_seed="events-development-0",dimension=8192,mode="bound",learning=True):
    component=fit_component(pairs,lexicon,seed=component_seed,dimension=8192,learning=learning)
    return EventModel(component,dimension=dimension,seed=event_seed,mode=mode)
````

## `release_tools.py`

原本: `PLM-L1-v0.7/release_tools.py`  
SHA256: `397dbd73529c1c5f7bdd19fad231f2ba89e1cf2d7fafec8720788c1dc17506bf`

````python
"""Additive freeze, old-release checks, demonstrations and immutable packaging."""
import argparse
import hashlib
import json
import zipfile
from evaluate import ROOT,source_files,verify_freeze
from evaluation_support import V06
from plm_l1_v06.algebra import digest
from plm_l1_v07.runtime import EventModel


def hashes(files,root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("freeze","check-baseline","demo","pack"))
    command=parser.parse_args().command
    if command=="freeze":
        manifest={"schema":"plm-l1-v07-source-freeze-v1","files":hashes(source_files(),ROOT)}
        write(ROOT/"SOURCE_MANIFEST.json",manifest)
        print(json.dumps({"files":len(manifest["files"]),"digest":digest(manifest)}))
    elif command=="check-baseline":
        baseline=json.loads((ROOT/"verification"/"PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        files=[]
        for name in ("PLM-L1-v0.1","PLM-L1-v0.2","PLM-L1-v0.3","PLM-L1-v0.4","PLM-L1-v0.5","PLM-L1-v0.6","PLM-P1-v0.2","PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent/name).rglob("*") if p.is_file())
            files.append(ROOT.parent/(name+".zip"))
        if hashes(files,ROOT.parent)!=baseline:
            raise ValueError("old release changed")
        old=ROOT.parent/"PLM-L1-v0.6"
        if hashes([p for p in old.rglob("*") if p.is_file()],old)!=hashes([p for p in V06.rglob("*") if p.is_file()],V06):
            raise ValueError("vendored v0.6 changed")
        print(json.dumps({"status":"unchanged","preserved_files":len(baseline),"vendor_files":len([p for p in V06.rglob("*") if p.is_file()])}))
    elif command=="demo":
        m=EventModel.load(ROOT/"results"/"model")
        texts=("太郎が花子を助けた。花子が太郎を助けなかった。","もし太郎が花子を助けたら。花子が健太を褒めなかった。",
               "太郎が花子を助けた。太郎が花子を助けた。","太郎が花子を助けた。彼が太郎を助けた。")
        rows=[]
        for index,text in enumerate(texts):
            r=m.read(text); row={"input":text,"status":r["status"],"reason":r.get("reason")}
            if r["status"]=="read":
                row["meaning"]=m.recover(r["packet"])["meaning"]
                row["generated"]=m.generate(r["packet"],["object","subject"])
                if index==0:
                    write(ROOT/"examples"/"MEANING.json",row["meaning"])
                    write(ROOT/"examples"/"MEANING_PACKET.json",r["packet"])
            rows.append(row)
        write(ROOT/"examples"/"ROUNDTRIPS.json",{"scope":"Human/evaluator only; original text is not generator input","demos":rows})
    else:
        verify_freeze()
        v=json.loads((ROOT/"verification"/"REPRODUCIBILITY.json").read_text(encoding="utf-8"))
        if v["status"]!="passed" or v["complete_numeric_runs"]!=2:
            raise ValueError("completed reproducibility verification required")
        archive=ROOT.parent/"PLM-L1-v0.7.zip"; checksum=ROOT.parent/"PLM-L1-v0.7.sha256"
        if archive.exists() or checksum.exists():
            raise ValueError("archive already exists")
        files=sorted(p for p in ROOT.rglob("*") if p.is_file() and p!=ROOT/"RELEASE_MANIFEST.json" and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0]!="work")
        write(ROOT/"RELEASE_MANIFEST.json",{"schema":"plm-l1-v07-release-v1","files":hashes(files,ROOT)})
        with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as stream:
            for path in files+[ROOT/"RELEASE_MANIFEST.json"]:
                stream.write(path,ROOT.name+"/"+path.relative_to(ROOT).as_posix())
        sha=hashlib.sha256(archive.read_bytes()).hexdigest()
        with checksum.open("x",encoding="utf-8") as stream:
            stream.write(sha+"  "+archive.name+"\n")
        print(json.dumps({"archive":str(archive),"bytes":archive.stat().st_size,"files":len(files)+1,"sha256":sha}))


if __name__=="__main__":
    main()
````

## `report.py`

原本: `PLM-L1-v0.7/report.py`  
SHA256: `fa0c3f98a9310b55b0567147bff9236bfb68670d4f08f6bf08314252916b30f1`

````python
"""Human-readable report derived from all measured successes and failures."""
from pathlib import Path


def write_report(output,result):
    lines=["# PLM-L1 v0.7 評価結果", "", "## 二事象の読解・生成", "", "|方式|読解・両事象完全一致|直接生成・意味と語順一致|往復・意味と語順一致|", "|---|---:|---:|---:|"]
    for mode in ("bound","partitioned"):
        rows=[r for r in result["standard"] if r["mode"]==mode]
        cells=[str(sum(r["counts"][s]["exact"] for r in rows))+"/"+str(sum(r["counts"][s]["requests"] for r in rows)) for s in ("read","generate","roundtrip")]
        lines.append("|"+mode+"|"+"|".join(cells)+"|")
    lines += ["", "一文ごとの正解ではなく、二つの出来事の五スロットと提示順を両方保持した場合だけ完全一致と数える。生成はさらに各文の指定語順を満たす必要がある。", "",
              "## 共有信号の低次元・符号なし対照", "", "|D|方式|復元正答|受理誤答|保留|異なる二事象の順番交換で信号が同じ|", "|---:|---|---:|---:|---:|---:|"]
    for d in sorted({r["dimension"] for r in result["codec"]}):
        for mode in ("bound","partitioned","unbound"):
            rows=[r for r in result["codec"] if r["dimension"]==d and r["mode"]==mode]
            counts={k:sum(r["counts"][k] for r in rows) for k in ("requests","exact","wrong","abstained")}
            distinct=[x for r in rows for x in r["records"] if x["distinct_events"]]
            lines.append(f'|{d}|{mode}|{counts["exact"]}/{counts["requests"]}|{counts["wrong"]}|{counts["abstained"]}|{sum(x["swapped_signal_equal"] for x in distinct)}/{len(distinct)}|')
    lines += ["", "unboundは事象の符号だけを外した対照。異なる出来事の順序が消える。partitionedは前半・後半を事象別に割り当てる対照で、同じD係数を持つ。比較予算は数値パケットの係数数だけであり、実行時の基底配列・全RAM・計算時間は一致させていない。", "",
              "## 共有信号への数値雑音（bound）", "", "|D|相対L2雑音|復元正答|受理誤答|保留|", "|---:|---:|---:|---:|---:|"]
    for d,level in sorted({(r["dimension"],r["level"]) for r in result["noise"]}):
        rows=[r for r in result["noise"] if r["dimension"]==d and r["level"]==level]
        c={k:sum(r["counts"][k] for r in rows) for k in ("requests","exact","wrong","abstained")}
        lines.append(f'|{d}|{level}|{c["exact"]}/{c["requests"]}|{c["wrong"]}|{c["abstained"]}|')
    lines += ["", "雑音試験は評価者の意味から直接作った数値信号の復元試験で、読解→通信→生成の実証ではない。P1観測マスクやS1チップ列・同期は統合していない。", "",
              "## 検証の範囲", "", f'固定受入：{sum(c["passed"] for c in result["checks"])}/{len(result["checks"])}。開発実行には合否判定を付けない。',
              "", "一事象の読解・生成部品はv0.6と同じ432対・同じseedで学習する。新しい事象符号のseedだけを変える。二事象の区切りと位置符号は設計したもので、二文対から学習したものではない。訓練APIに二事象例や評価正解は渡していない。",
              "", "二文は明示的な句点で分割する。提示順と各事象の役割・否定・仮定を扱い、時系列・因果・代名詞・省略・矛盾解消・自由長文は扱わない。生成器へ原文や意味のJSON一覧を転送せず、一つの数値パケットと二つの出力語順指定だけを渡す。意味スロットの復元後には通常Pythonによる制御処理が残る。",
              "", "新しい二文の組合せを既存の制御文法と語彙から構築した試験で、独立に収集した自然文の評価ではない。partitioned対照も成功する場合、共有SS符号化が唯一の方法・性能上優越すると主張しない。v0.6の記憶負荷偏り問題を解消した実験でもない。", ""]
    (Path(output)/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
````

## `requirements.txt`

原本: `PLM-L1-v0.7/requirements.txt`  
SHA256: `7bd6b8946940b79948c548c8048e545684b91c8edc9444d8dfc0c8f76a97c0a7`

````text
numpy==2.3.5
````

## `tests/test_events.py`

原本: `PLM-L1-v0.7/tests/test_events.py`  
SHA256: `3582c414a2cb43a0414b37b2f766856da0049f14f1fe1cd7fdb682ecf2824afc`

````python
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import canonical
from plm_l1_v06.runtime import Model as ComponentModel
from plm_l1_v06.lexicon import ROLES
from plm_l1_v07.runtime import EventModel,PACKET_FIELDS
from plm_l1_v07.training import fit
from evaluation_support import data,GOAL_PAIRS,parse_document,document_goals,render,V06
from measurements import INVALID_TEXTS,bad_packets,unique_rows,confusion,count_rows


class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=fit(data("folds/object_negative/train"),data("lexicon"))
        cls.rows=data("events_development")
        cls.meaning={"events":[{"subject":"entity:太郎","object":"entity:花子","predicate":"predicate:help","polarity":"polarity:positive","modality":"modality:asserted"},
                               {"subject":"entity:花子","object":"entity:太郎","predicate":"predicate:help","polarity":"polarity:negative","modality":"modality:asserted"}]}
        cls.text="太郎が花子を助けた。花子が太郎を助けなかった。"
        cls.packet=cls.model.encode(cls.meaning)

    def test_all_development_documents_read(self):
        for row in self.rows:
            out=self.model.read(row["text"])
            self.assertEqual(out["status"],"read",row["id"])
            self.assertEqual(self.model.recover(out["packet"])["meaning"],row["meaning"])

    def test_all_development_meanings_all_goal_pairs(self):
        for row in unique_rows("development"):
            for goals in GOAL_PAIRS:
                out=self.model.generate(self.model.encode(row["meaning"]),goals)
                self.assertEqual(parse_document(out["text"]),row["meaning"])
                self.assertEqual(document_goals(out["text"]),goals)

    def test_role_reversal_and_negative_scope(self):
        out=self.model.generate(self.model.read(self.text)["packet"],["object","object"])
        self.assertEqual(out["text"],"花子を太郎が助けた。太郎を花子が助けなかった。")

    def test_modality_stays_with_its_event(self):
        text="もし太郎が花子を助けたら。花子が太郎を助けなかった。"
        r=self.model.read(text)
        out=self.model.generate(r["packet"],["subject","object"])
        self.assertEqual(out["text"],"もし太郎が花子を助けたら。太郎を花子が助けなかった。")

    def test_identical_mentions_not_deduplicated(self):
        m={"events":[self.meaning["events"][0]]*2}
        out=self.model.generate(self.model.encode(m))
        self.assertEqual(out["text"],"太郎が花子を助けた。太郎が花子を助けた。")

    def test_event_order_is_preserved(self):
        m={"events":list(reversed(self.meaning["events"]))}
        out=self.model.generate(self.model.encode(m))
        self.assertEqual(parse_document(out["text"]),m)
        self.assertNotEqual(out["text"],self.text)

    def test_event_binding_distinguishes_swapped_events(self):
        c=self.model.codec
        self.assertFalse(np.array_equal(c.encode(self.meaning),c.encode({"events":list(reversed(self.meaning["events"]))})))

    def test_unbound_control_loses_order_exactly(self):
        m=EventModel(self.model.component,mode="unbound")
        self.assertTrue(np.array_equal(m.codec.encode(self.meaning),m.codec.encode({"events":list(reversed(self.meaning["events"]))})))

    def test_partitioned_control_same_numeric_budget(self):
        m=EventModel(self.model.component,mode="partitioned")
        self.assertEqual(m.codec.encode(self.meaning).nbytes,self.model.codec.encode(self.meaning).nbytes)
        self.assertEqual(m.recover(m.encode(self.meaning))["meaning"],self.meaning)

    def test_absent_second_event_rejected(self):
        c=self.model.codec; event=self.meaning["events"][0]
        v=c.presence[0].copy()
        for role in ROLES:
            v+=c.codes[0][role][c.candidates[role].index(event[role])]
        v*=c.scale
        p=dict(self.packet,real=v.real.tolist(),imag=v.imag.tolist())
        self.assertEqual(self.model.recover(p)["status"],"abstain")

    def test_numeric_packet_has_no_event_list_or_subpackets(self):
        self.assertEqual(set(self.packet),PACKET_FIELDS)
        self.assertEqual(len(self.packet["real"]),8192)
        self.assertEqual(len(self.packet["imag"]),8192)
        self.assertNotIn("太郎",canonical(self.packet))
        self.assertNotIn("events",canonical(self.packet))

    def test_bad_packets_rejected(self):
        for packet in bad_packets(self.model,self.meaning):
            self.assertEqual(self.model.generate(packet)["status"],"abstain")

    def test_cross_model_packet_rejected(self):
        for other in (EventModel(self.model.component,seed="another"),EventModel(self.model.component,mode="partitioned")):
            self.assertEqual(other.generate(self.packet)["reason"],"packet_model_mismatch")

    def test_old_single_event_packet_rejected(self):
        p=self.model.component.encode(self.meaning["events"][0])
        self.assertEqual(self.model.generate(p)["status"],"abstain")

    def test_packet_extra_gold_source_hint_rejected(self):
        for field in ("events","source","meaning","event_hints","subpackets","gold"):
            self.assertEqual(self.model.generate(dict(self.packet,**{field:self.meaning}))["status"],"abstain")

    def test_bad_event_count_and_fields(self):
        for meaning in (None,[],{},self.meaning["events"],{"events":[]},{"events":self.meaning["events"][:1]},
                        {"events":self.meaning["events"]+[self.meaning["events"][0]]},dict(self.meaning,order=[0,1])):
            with self.assertRaises(ValueError):
                self.model.encode(meaning)

    def test_unknown_semantic_value_rejected(self):
        m=copy.deepcopy(self.meaning); m["events"][1]["subject"]="entity:未知"
        with self.assertRaises(ValueError):
            self.model.encode(m)

    def test_input_not_mutated(self):
        m=copy.deepcopy(self.meaning)
        self.model.encode(m)
        self.assertEqual(m,self.meaning)
        p=copy.deepcopy(self.packet)
        self.model.generate(p)
        self.assertEqual(p,self.packet)

    def test_invalid_documents_rejected(self):
        for text in INVALID_TEXTS+(None,[],True,1):
            self.assertEqual(self.model.read(text)["status"],"abstain")

    def test_only_between_sentence_whitespace_allowed(self):
        out=self.model.read("太郎が花子を助けた。\n花子が太郎を助けなかった。")
        self.assertEqual(self.model.recover(out["packet"])["meaning"],self.meaning)
        self.assertEqual(self.model.read("太郎 が花子を助けた。花子が太郎を助けなかった。")["status"],"abstain")

    def test_bad_goals_rejected(self):
        for goals in (None,"subject",[],["subject"],["subject"]*3,["subject","essay"],["subject",[]]):
            self.assertEqual(self.model.generate(self.packet,goals)["status"],"abstain")

    def test_no_partial_generation_on_second_event_failure(self):
        with patch.object(self.model.component,"generate",side_effect=[{"status":"generated","text":"first"},{"status":"abstain","reason":"unit_failure"}]):
            out=self.model.generate(self.packet)
        self.assertEqual(out["status"],"abstain")
        self.assertIsNone(out["text"])

    def test_no_partial_packet_on_second_event_failure(self):
        out=self.model.read("太郎が花子を助けた。彼が太郎を助けた。")
        self.assertEqual(out["status"],"abstain")
        self.assertIsNone(out["packet"])

    def test_reader_requires_recoverable_shared_signal(self):
        with patch.object(EventModel,"recover",return_value={"status":"abstain","meaning":None}):
            out=self.model.read(self.text)
        self.assertEqual(out["reason"],"two_event_signal_unrecoverable")
        self.assertIsNone(out["packet"])

    def test_reader_requires_both_candidate_matches(self):
        wrong={"events":list(reversed(self.meaning["events"]))}
        with patch.object(EventModel,"recover",return_value={"status":"recovered","meaning":wrong}):
            out=self.model.read(self.text)
        self.assertEqual(out["reason"],"two_event_signal_mismatch")

    def test_generation_never_calls_reader(self):
        with patch.object(EventModel,"read",side_effect=AssertionError()),patch.object(ComponentModel,"read",side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.packet)["text"],self.text)

    def test_no_runtime_feature_learning_or_oracle(self):
        with patch("plm_l1_v06.banked.dependency_leaves",side_effect=AssertionError()),patch("plm_l1.teacher.surface",side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.model.read(self.text)["packet"])["text"],self.text)

    def test_no_learning_ablation(self):
        m=fit(data("folds/object_negative/train"),data("lexicon"),learning=False)
        self.assertEqual(m.read(self.text)["status"],"abstain")
        self.assertEqual(m.generate(m.encode(self.meaning))["status"],"abstain")

    def test_component_primary_weights_unchanged(self):
        old=ComponentModel.load(V06/"results"/"model")
        self.assertEqual(old.fingerprint,self.model.component.fingerprint)
        for name,memory in old.memories.items():
            for a,b in zip(memory.blocks,self.model.component.memories[name].blocks):
                self.assertEqual(a.blob,b.blob)

    def test_two_event_binding_is_explicitly_not_learned(self):
        self.assertEqual(self.model.meta["binding_learning"],"designed_not_learned")
        self.assertEqual(self.model.component.meta["pair_count"],432)

    def test_inference_remains_disabled(self):
        for out in (self.packet,self.model.read(self.text),self.model.generate(self.packet),self.model.recover(self.packet)):
            self.assertIs(out["eligible_for_inference"],False)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            m=EventModel.load(directory)
            self.assertEqual(m.fingerprint,self.model.fingerprint)
            self.assertEqual(m.generate(self.packet),self.model.generate(self.packet))

    def test_save_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            with self.assertRaises(ValueError):
                self.model.save(directory)

    def test_metadata_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            p=Path(directory)/"model.json"; info=json.loads(p.read_text(encoding="utf-8"))
            info["metadata"]["event_positions"]="causal_order"
            p.write_text(json.dumps(info),encoding="utf-8")
            with self.assertRaises(ValueError):
                EventModel.load(directory)

    def test_invalid_codec_config(self):
        for kwargs in ({"dimension":64},{"dimension":192},{"seed":""},{"mode":"unknown"},{"mode":[]}):
            with self.assertRaises(ValueError):
                EventModel(self.model.component,**kwargs)

    def test_development_and_evaluation_pairs_disjoint(self):
        a={canonical(r["meaning"]) for r in self.rows}
        b={canonical(r["meaning"]) for r in data("events_evaluation")}
        self.assertEqual((len(a),len(b),len(a&b)),(72,72,0))

    def test_all_nine_categories_and_four_goal_pairs(self):
        for split in ("development","evaluation"):
            rows=data("events_"+split)
            self.assertEqual(len(rows),288)
            self.assertEqual(len({r["category"] for r in rows}),9)
            self.assertTrue(all(parse_document(r["text"])==r["meaning"] for r in rows))

    def test_order_error_not_hidden_by_bag_scoring(self):
        wrong={"events":list(reversed(self.meaning["events"]))}
        self.assertTrue(confusion(wrong,self.meaning)["event_swapped"])
        self.assertGreater(confusion(wrong,self.meaning)["cross_event_slots"],0)

    def test_valid_semantic_change_is_not_authentication(self):
        other=copy.deepcopy(self.meaning); other["events"][1]["polarity"]="polarity:positive"
        out=self.model.generate(self.model.encode(other))
        self.assertEqual(parse_document(out["text"]),other)
        self.assertNotEqual(parse_document(out["text"]),self.meaning)

    def test_count_keeps_wrong_and_abstention_separate(self):
        rows=[{"stage":"read","accepted":True,"exact":True},{"stage":"read","accepted":True,"exact":False},{"stage":"read","accepted":False,"exact":False}]
        self.assertEqual(count_rows(rows)["read"],{"requests":3,"accepted":2,"exact":1,"wrong":1,"abstained":1})


if __name__=="__main__":
    unittest.main()
````

## `verify_release.py`

原本: `PLM-L1-v0.7/verify_release.py`  
SHA256: `e651221e8ba1445e90c209aac343f757a438117a6b907d349c298af858e10edd`

````python
"""Test all versions, verify result integrity, isolate training and generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from evaluate import verify_freeze,judge
from evaluation_support import ROOT,V06,V05,V04,V03,V02,V01,data,parse_document,document_goals
from plm_l1_v06.algebra import digest
from plm_l1_v07.runtime import EventModel,PACKET_FIELDS


def run(arguments,cwd,output,label,expected=0):
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",PYTHONIOENCODING="utf-8",PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH",None)
    result=subprocess.run([sys.executable,"-B",*arguments],cwd=cwd,env=env,capture_output=True,text=True,encoding="utf-8",timeout=240)
    log=result.stdout+result.stderr
    (output/(label+".log")).write_text(log,encoding="utf-8")
    if result.returncode!=expected:
        raise ValueError(label+" failed: "+log[-3000:])
    return result.stdout,log


def copy_package(source,target,excluded=()):
    target.mkdir(parents=True)
    for path in sorted(source.glob("*.py")):
        if path.name not in excluded:
            shutil.copyfile(path,target/path.name)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--preflight",action="store_true")
    args=parser.parse_args()
    output=Path(args.out).resolve()
    if output.exists():
        raise ValueError("fresh verification directory required")
    output.mkdir(parents=True)
    p=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
    if args.preflight:
        from plm_l1_v07.training import fit
        model=fit(data("folds/"+p["component_fold"]+"/train"),data("lexicon"),component_seed=p["component_seed"],event_seed=p["development_seeds"][0])
        freeze,claimed,checks="preflight_not_frozen",None,[]
    else:
        freeze=verify_freeze()
        r=json.loads((ROOT/"results"/"EVALUATION.json").read_text(encoding="utf-8"))
        claimed=r.pop("result_digest")
        if digest(r)!=claimed or r["freeze_hash"]!=freeze:
            raise ValueError("evaluation integrity failure")
        checks=judge(r,p)
        if checks!=r["checks"] or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        model=EventModel.load(ROOT/"results"/"model")
        if model.fingerprint!=r["standard"][0]["fingerprint"] or model.component.fingerprint!=r["component_fingerprint"]:
            raise ValueError("saved model differs from evaluation")
    test_counts={}
    for label,cwd in (("NEW_TESTS",ROOT),("V06_TESTS",V06),("V05_TESTS",V05),("V04_TESTS",V04),("V03_TESTS",V03),("V02_TESTS",V02),("V01_TESTS",V01)):
        _,log=run(["-m","unittest","discover","-s","tests","-v"],cwd,output,label)
        test_counts[label]=int(re.search(r"Ran (\d+) tests",log).group(1))
    training=output/"pair-training-only"
    for name in ("plm_l1_v07","plm_l1_v06"):
        copy_package(ROOT/name,training/name)
    shutil.copyfile(ROOT/"data"/"folds"/p["component_fold"]/"train.json",training/"train.json")
    shutil.copyfile(ROOT/"data"/"lexicon.json",training/"lexicon.json")
    assertion="from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert not Path('events_evaluation.json').exists(); assert all(importlib.util.find_spec(n) is None for n in ('evaluation_support','plm_l1_v05','plm_l1')); print('only current component package and single-event training pairs; no two-event corpus or legacy teacher')"
    run(["-c",assertion],training,output,"PAIR_TRAIN_BOUNDARY")
    stdout,_=run(["-m","plm_l1_v07","train","--pairs","train.json","--lexicon","lexicon.json","--component-seed",model.component.meta["seed"],"--event-seed",model.meta["seed"],"--dimension",str(model.meta["dimension"]),"--mode",model.meta["mode"],"--out","model"],training,output,"PAIR_TRAIN")
    if json.loads(stdout)["fingerprint"]!=model.fingerprint:
        raise ValueError("isolated learning differs")
    generation=output/"generation-only"
    for name in ("plm_l1_v07","plm_l1_v06"):
        copy_package(ROOT/name,generation/name,{"reader.py","training.py"})
    shutil.copytree(training/"model",generation/"model")
    assertion="from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('plm_l1_v07.reader','plm_l1_v07.training','plm_l1_v06.reader','plm_l1_v06.training','evaluation_support','plm_l1_v05','plm_l1')); assert not Path('train.json').exists(); print('no reader or training entrypoints, original texts, event corpus, or legacy teacher; shared weights/helpers remain')"
    run(["-c",assertion],generation,output,"GENERATION_BOUNDARY")
    texts=("太郎が花子を助けた。花子が太郎を助けなかった。","もし太郎が花子を助けたら。花子が健太を褒めなかった。",
           "太郎が花子を助けた。太郎が美咲を訪ねた。","太郎が花子を助けた。太郎が花子を助けた。")
    demos=[]
    for index,text in enumerate(texts):
        name=f"packet-{index}.json"
        run(["-m","plm_l1_v07","read","--model","model","--text",text,"--out",name],training,output,f"READ_{index}")
        packet=json.loads((training/name).read_text(encoding="utf-8"))
        if set(packet)!=PACKET_FIELDS or any(type(x) not in (float,int) for k in ("real","imag") for x in packet[k]):
            raise ValueError("non-numerical transfer")
        shutil.copyfile(training/name,generation/name)
        stdout,_=run(["-m","plm_l1_v07","generate","--model","model","--packet",name,"--goals","object","subject"],generation,output,f"GENERATE_{index}")
        out=json.loads(stdout)
        if out["status"]!="generated" or parse_document(out["text"])!=parse_document(text) or document_goals(out["text"])!=["object","subject"]:
            raise ValueError("isolated event generation failed")
        demos.append({"input_for_verifier_only":text,"output":out["text"],"both_events_meaning_and_goals_exact":True})
    assertion="import json; from unittest.mock import patch; from plm_l1_v07.runtime import EventModel; m=EventModel.load('model'); p=json.load(open('packet-0.json',encoding='utf-8')); guard=patch('plm_l1_v06.banked.dependency_leaves',side_effect=AssertionError('runtime retraining')); guard.start(); assert m.generate(p)['status']=='generated'; print('no runtime feature learning')"
    run(["-c",assertion],generation,output,"NO_RUNTIME_FEATURE_LEARNING")
    run(["-m","plm_l1_v07","read","--model","model","--text","太郎が花子を助けた。彼が太郎を助けた。","--out","must-not-exist.json"],training,output,"ATOMIC_ABSTAIN",expected=2)
    if (training/"must-not-exist.json").exists():
        raise ValueError("partial document packet emitted")
    manifest_path=ROOT/"RELEASE_MANIFEST.json"
    manifest_checked=False
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob("*") if p.is_file() and p!=manifest_path and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0]!="work"}
        if actual!=manifest["files"]:
            raise ValueError("release file inventory or bytes changed")
        manifest_checked=True
    report={"status":"passed","preflight":args.preflight,"source_freeze":freeze,"result_digest":claimed,"acceptance_checks":len(checks),"test_counts":test_counts,
            "single_event_pair_training_only":True,"two_event_training_examples":0,"isolated_model_fingerprint_equal":True,"model_fingerprint":model.fingerprint,
            "component_fingerprint":model.component.fingerprint,"generation_without_both_reader_and_training_entrypoints":True,"single_numerical_packet_only_transfer":True,
            "atomic_abstention_without_partial_packet":True,"no_runtime_feature_learning":True,"isolated_roundtrips":demos,
            "boundary_limit":"Shared learned v0.6 component weights and helpers remain; two-event boundaries/bindings are designed, not learned.",
            "release_manifest_checked":manifest_checked,"full_numeric_rerun_in_this_command":False,"python":sys.version}
    (output/"VERIFICATION.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
````

