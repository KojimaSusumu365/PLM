from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    """Unseen seeds authored only after the C2 v0.1 engine was frozen."""
    return [
        {"id":"sentence_decimal_target","inputs":"A dog weighs 3.5 kg. In a separate case, a cat slept.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2","sentence_boundary","target_tracking","decimal","abstention","en"]},
        {"id":"temporal_thereafter","inputs":["A dog was examined.","Thereafter, a cat was examined."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2","temporal_relation","target_tracking","abstention","en"]},
        {"id":"temporal_following_inline","inputs":"A dog was cataloged. Following that, a cat was cataloged.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2","temporal_relation","sentence_boundary","abstention","en"]},
        {"id":"revision_original_revised","inputs":"Originally labeled a dog. Revised finding: cat.","domain":"entity","expected":"CAT","tags":["challenge_c2","revision_relation","sentence_boundary","en"]},
        {"id":"revision_retract_revise","inputs":"The original dog finding was ruled out. The revised record says cat.","domain":"entity","expected":"CAT","tags":["challenge_c2","revision_relation","retraction","en"]},
        {"id":"irregular_bitten","inputs":"The animal had been bitten.","domain":"action","expected":"BITE","tags":["challenge_c2","irregular_lemma","en"]},
        {"id":"irregular_boundary_bitter","inputs":"A bitter taste remained.","domain":"action","expected":"UNRESOLVED","forbidden":["BITE"],"tags":["challenge_c2","irregular_lemma","boundary","abstention","en"]},
        {"id":"compound_riverbank","inputs":"They rested on the riverbank.","domain":"place","expected":"RIVER_BANK","tags":["challenge_c2","closed_compound","en"]},
        {"id":"compound_riverbanks_plural","inputs":"The riverbanks were muddy.","domain":"place","expected":"RIVER_BANK","tags":["challenge_c2","closed_compound","plural","en"]},
        {"id":"relation_river_statistics","inputs":"The bank reviewed river statistics for a report.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2","typed_relation","non_spatial","abstention","en"]},
        {"id":"relation_near_river","inputs":"The bank is near the river.","domain":"place","expected":"RIVER_BANK","tags":["challenge_c2","typed_relation","spatial","en"]},
        {"id":"relation_nowhere_river","inputs":"The bank is nowhere near the river.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2","typed_relation","negation","abstention","en"]},
        {"id":"relation_account_river_levels","inputs":"The bank keeps an account of river levels.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2","typed_relation","competing_context","en"]},
        {"id":"consensus_source_siblings","inputs":["Source A reports a dog.","Source B reports a cat."],"domain":"entity","expected":"ANIMAL","tags":["challenge_c2","consensus","hierarchy","source_order","en"]},
        {"id":"open_set_otter","inputs":"The otter floated quietly.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2","open_set","abstention","en"]},
        {"id":"revision_colon","inputs":"Originally labeled a dog: revised finding labels it a cat.","domain":"entity","expected":"CAT","tags":["challenge_c2","revision_relation","unseen_boundary","en"]},
        {"id":"target_meanwhile","inputs":["A dog was recorded.","Meanwhile, a cat was recorded elsewhere."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2","target_tracking","unseen_marker","abstention","en"]},
        {"id":"relation_sponsored_cleanup","inputs":"The bank sponsored a river cleanup project.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2","typed_relation","affordance","world_knowledge","en"]},
        {"id":"correction_rather","inputs":"It was not a dog, rather a cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2","polarity","correction","unseen_marker","en"]},
        {"id":"coreference_latter","inputs":["A dog and a cat were observed.","The latter was selected."],"domain":"entity","expected":"CAT","tags":["challenge_c2","coreference","anaphora","en"]},
    ]


def wrap(inputs, prefix):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}"
    return [f"{prefix}{value}" for value in inputs]


def build():
    semantic_seeds = seeds()
    if len(semantic_seeds) != 20:
        raise ValueError(f"Expected 20 seeds, got {len(semantic_seeds)}")
    wrappers = (("raw", ""), ("record", "Record: "), ("observation", "Observation: "))
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
        "dataset": "PLM-C2-v0.1-post-implementation-challenge",
        "schema_version": 2,
        "construction": "20 unseen semantic seeds x 3 deterministic wrappers",
        "limitations": [
            "Authored in the same development session; not an external corpus.",
            "The C2 v0.1 engine was frozen before this file's first evaluation run.",
            "No engine or Concept-data tuning is permitted after the first run.",
            "Wrappers are dependent and must be cluster-bootstrapped by template_group.",
        ],
        "splits": {"dev": 0, "test": 60, "all": 60},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the frozen PLM-C2 v0.1 challenge set.")
    parser.add_argument("--out", default="data/challenge_c2_v01.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
