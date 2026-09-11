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
