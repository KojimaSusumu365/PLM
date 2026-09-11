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
