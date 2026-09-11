from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    """Unseen seeds authored only after the v0.3 engine was frozen."""
    return [
        {"id":"morph_puppies_sleep","inputs":"Several puppies were asleep.","domain":"entity","expected":"DOG","tags":["challenge_v03","morphology","irregular_plural","en"]},
        {"id":"morph_barked_loudly","inputs":"The animal barked loudly.","domain":"action","expected":"BARK","tags":["challenge_v03","morphology","past_tense","en"]},
        {"id":"morph_vocalizing","inputs":"The animal was vocalizing.","domain":"action","expected":"VOCALIZE","tags":["challenge_v03","morphology","progressive","en"]},
        {"id":"morph_false_positive_cared","inputs":"The person cared deeply.","domain":"entity","expected":"HUMAN","forbidden":["VEHICLE"],"tags":["challenge_v03","morphology","boundary","en"]},
        {"id":"revision_preliminary_verified","inputs":"Preliminary finding: dog; verified finding: cat.","domain":"entity","expected":"CAT","tags":["challenge_v03","discourse","correction","en"]},
        {"id":"revision_ruled_out","inputs":"The dog classification was ruled out; the cat classification remained.","domain":"entity","expected":"CAT","tags":["challenge_v03","discourse","retraction","en"]},
        {"id":"revision_tekai_ja","inputs":"犬という判定を撤回、猫を確認済み","domain":"entity","expected":"CAT","tags":["challenge_v03","discourse","retraction","ja"]},
        {"id":"revision_financial","inputs":"Previously called a river bank; conclusively established as a bank with accounts.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_v03","discourse","correction","relation","en"]},
        {"id":"target_another_instance","inputs":["A dog was logged.","Another instance contains a cat."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_v03","target_tracking","abstention","en"]},
        {"id":"target_separate_case_inline","inputs":"A dog was logged. In a separate case, a cat was logged.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_v03","target_tracking","clause_boundary","abstention","en"]},
        {"id":"target_betsu_taisho_ja","inputs":["犬を記録した","別の対象は猫だった"],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_v03","target_tracking","abstention","ja"]},
        {"id":"consensus_another_source","inputs":["One source reports a dog.","Another source reports a cat."],"domain":"entity","expected":"ANIMAL","tags":["challenge_v03","consensus","hierarchy","source_order","en"]},
        {"id":"open_set_quokka","inputs":"The quokka rested quietly.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_v03","open_set","abstention","en"]},
        {"id":"coordination_bite","inputs":"A dog did not bark but did bite.","domain":"action","expected":"BITE","forbidden":["BARK"],"tags":["challenge_v03","polarity","coordination","en"]},
        {"id":"compound_riverfront","inputs":"The bank runs along the riverfront.","domain":"place","expected":"RIVER_BANK","tags":["challenge_v03","compound","relation","spatial","en"]},
        {"id":"relation_river_statistics","inputs":"The bank reviewed river statistics for a report.","domain":"place","expected":"UNRESOLVED","tags":["challenge_v03","relation","non_spatial","abstention","en"]},
        {"id":"target_subsequently","inputs":["A dog was examined.","Subsequently, a cat was examined in another room."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_v03","target_tracking","unseen_marker","abstention","en"]},
        {"id":"revision_originally_revised","inputs":"Originally labeled a dog; the revised finding labels it a cat.","domain":"entity","expected":"CAT","tags":["challenge_v03","discourse","unseen_marker","en"]},
        {"id":"morph_bitten","inputs":"The animal had bitten the toy.","domain":"action","expected":"BITE","tags":["challenge_v03","morphology","irregular_participle","en"]},
        {"id":"compound_riverbank_closed","inputs":"They rested on the riverbank.","domain":"place","expected":"RIVER_BANK","tags":["challenge_v03","compound","closed_compound","en"]},
    ]


def wrap(inputs, prefix):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}"
    return [f"{prefix}{value}" for value in inputs]


def build():
    semantic_seeds = seeds()
    if len(semantic_seeds) != 20:
        raise ValueError(f"Expected 20 seeds, got {len(semantic_seeds)}")
    wrappers = (("raw", ""), ("observation", "Observation: "), ("transcript", "Transcript: "))
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
        "dataset": "PLM-C1-v0.3-post-implementation-challenge",
        "schema_version": 2,
        "construction": "20 unseen semantic seeds x 3 deterministic wrappers",
        "limitations": [
            "Authored in the same development session; not an external corpus.",
            "The v0.3 engine was frozen before this file's first evaluation run.",
            "No engine or Concept-data tuning is permitted after the first run.",
            "Wrappers are dependent and must be cluster-bootstrapped by template_group.",
        ],
        "splits": {"dev": 0, "test": 60, "all": 60},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the frozen PLM-C1 v0.3 challenge set.")
    parser.add_argument("--out", default="data/challenge_c1_v03.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
