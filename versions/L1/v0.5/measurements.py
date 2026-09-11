"""Independent scoring and explicitly separated numerical stress experiments."""
import copy
import hashlib
import json
import numpy as np
from plm_l1_v05.algebra import Book, canonical, require
from plm_l1_v05.projection import Space, fit_memory
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
