from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    return [
        {"id":"correction_initially_en","inputs":"Initially it was identified as a dog; later it was confirmed to be a cat.","domain":"entity","expected":"CAT","tags":["challenge","correction","unseen_marker","en"]},
        {"id":"correction_initially_ja","inputs":"当初は犬、後に猫と判明した","domain":"entity","expected":"CAT","tags":["challenge","correction","unseen_marker","ja"]},
        {"id":"correction_update_en","inputs":["It is a dog.","Update: it is a cat."],"domain":"entity","expected":"CAT","tags":["challenge","correction","source_order","en"]},
        {"id":"correction_however_en","inputs":"It was called a dog; however, it was a cat.","domain":"entity","expected":"CAT","tags":["challenge","correction","unseen_marker","en"]},
        {"id":"correction_actually_dash_en","inputs":"The dog—actually, the cat—was seen.","domain":"entity","expected":"CAT","tags":["challenge","correction","unseen_marker","en"]},
        {"id":"correction_iya_ja","inputs":"犬、いや猫だった","domain":"entity","expected":"CAT","tags":["challenge","correction","unseen_marker","ja"]},
        {"id":"double_negation_en","inputs":"It is not impossible that this is a dog.","domain":"entity","expected":"DOG","tags":["challenge","negation","double_negation","en"]},
        {"id":"double_negation_ja","inputs":"犬でないとは言えない","domain":"entity","expected":"DOG","tags":["challenge","negation","double_negation","ja"]},
        {"id":"reported_denial_en","inputs":"The report denied that it was a dog.","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["challenge","negation","reported_speech","abstention","en"]},
        {"id":"predicate_scope_ja","inputs":"犬は吠えたわけではなかった","domain":"action","expected":"UNRESOLVED","forbidden":["BARK"],"tags":["challenge","negation","predicate","abstention","ja"]},
        {"id":"context_plural_account","inputs":"The bank stopped opening accounts.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge","context_scope","morphology","en"]},
        {"id":"context_conditional_water","inputs":"If there were water, the bank would flood.","domain":"place","expected":"UNRESOLVED","tags":["challenge","context_scope","conditional","abstention","en"]},
        {"id":"context_nowhere_river","inputs":"The bank is nowhere near a river.","domain":"place","expected":"UNRESOLVED","tags":["challenge","context_scope","negation","abstention","en"]},
        {"id":"context_negated_river_ja","inputs":"bankの近くに川はない","domain":"place","expected":"UNRESOLVED","tags":["challenge","context_scope","negation","abstention","mixed"]},
        {"id":"context_separate_sentences","inputs":"The bank was mentioned. Water spilled from a glass.","domain":"place","expected":"UNRESOLVED","tags":["challenge","context_scope","clause_boundary","abstention","en"]},
        {"id":"scope_afterward_sources","inputs":["I visited a bank.","Afterward I crossed a river."],"domain":"place","expected":"UNRESOLVED","tags":["challenge","instance_scope","unseen_marker","abstention","en"]},
        {"id":"scope_sonogo_sources","inputs":["銀行へ行った","その後、川岸を歩いた"],"domain":"place","expected":"UNRESOLVED","tags":["challenge","instance_scope","unseen_marker","abstention","ja"]},
        {"id":"scope_separately_entities","inputs":["A dog was recorded.","Separately, a cat was recorded."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge","instance_scope","abstention","en"]},
        {"id":"correction_financial","inputs":"It seemed to be a river bank; actually it was a bank account.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge","correction","context_scope","en"]},
        {"id":"multiple_instances_parent","inputs":["A dog was recorded.","A cat was recorded."],"domain":"entity","expected":"ANIMAL","tags":["challenge","consensus","hierarchy","en"]}
    ]


def wrap(inputs, prefix):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}"
    return [f"{prefix}{value}" for value in inputs]


def build():
    semantic_seeds = seeds()
    if len(semantic_seeds) != 20:
        raise ValueError(f"Expected 20 seeds, got {len(semantic_seeds)}")
    wrappers = (("raw", ""), ("record", "Record: "), ("note", "Note: "))
    cases = []
    for seed in semantic_seeds:
        for variant, prefix in wrappers:
            case = dict(seed)
            case["id"] = f"{seed['id']}__{variant}"
            case["template_group"] = seed["id"]
            case["split"] = "test"
            case["inputs"] = wrap(seed["inputs"], prefix)
            case["tags"] = sorted(set(seed["tags"] + ["test"]))
            cases.append(case)
    return {
        "dataset": "PLM-C1-v0.1-post-implementation-challenge",
        "schema_version": 2,
        "construction": "20 unseen semantic seeds x 3 deterministic wrappers",
        "limitations": [
            "Authored in the same development session; not an external corpus.",
            "Frozen before the first run and not used to tune PLM-C1 v0.1.",
            "Wrappers are dependent and must be cluster-bootstrapped by template_group.",
        ],
        "splits": {"dev": 0, "test": 60, "all": 60},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the frozen PLM-C1 v0.1 challenge set.")
    parser.add_argument("--out", default="data/challenge_c1_v01.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
