from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    """Unseen seeds authored only after the C2 v0.2 engine was frozen."""
    return [
        {"id":"coreference_former","inputs":["A cat and a dog were photographed.","The former received a tag."],"domain":"entity","expected":"CAT","tags":["challenge_c2_v02","coreference","ordered_reference","en"]},
        {"id":"coreference_first","inputs":["A dog and a cat entered the room.","The first was examined."],"domain":"entity","expected":"DOG","tags":["challenge_c2_v02","coreference","ordinal","en"]},
        {"id":"coreference_second","inputs":["A dog and a cat waited outside.","The second was admitted."],"domain":"entity","expected":"CAT","tags":["challenge_c2_v02","coreference","ordinal","en"]},
        {"id":"coreference_nearest_pair","inputs":["A vehicle was parked.","A dog and a cat waited nearby.","The latter moved."],"domain":"entity","expected":"CAT","tags":["challenge_c2_v02","coreference","nearest_antecedent","en"]},
        {"id":"coreference_missing_antecedent","inputs":"The latter was quiet.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2_v02","coreference","open_set","abstention","en"]},
        {"id":"correction_instead","inputs":"The provisional record said dog, instead cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2_v02","correction","instead","en"]},
        {"id":"correction_or_rather","inputs":"The animal was logged as a dog, or rather a cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2_v02","correction","rather","en"]},
        {"id":"correction_rather_clause","inputs":"It was a dog; rather, it was a cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2_v02","correction","rather","en"]},
        {"id":"comparative_rather_than","inputs":"A dog rather than an otter was selected.","domain":"entity","expected":"DOG","tags":["challenge_c2_v02","correction_boundary","negative_control","en"]},
        {"id":"revision_amended_colon","inputs":"Originally marked dog: amended record says cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2_v02","revision","colon_boundary","en"]},
        {"id":"revision_updated_colon","inputs":"At the outset it was dog: updated finding identifies cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2_v02","revision","colon_boundary","en"]},
        {"id":"revision_reclassified_colon","inputs":"Originally marked dog: reclassified as cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["challenge_c2_v02","revision","unseen_role","en"]},
        {"id":"agentive_funded","inputs":"The bank funded a river restoration project.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v02","agentive_relation","affordance","en"]},
        {"id":"agentive_financed","inputs":"The bank financed research on river pollution.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v02","agentive_relation","affordance","en"]},
        {"id":"agentive_underwrote","inputs":"The bank underwrote a river conservation program.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v02","agentive_relation","affordance","en"]},
        {"id":"agentive_lent","inputs":"The bank lent equipment to a river cleanup team.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v02","agentive_relation","affordance","en"]},
        {"id":"agentive_negated","inputs":"The bank never funded a river study.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2_v02","agentive_relation","negation","abstention","en"]},
        {"id":"agentive_hypothetical","inputs":"If the bank funded a river survey, it would announce it.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2_v02","agentive_relation","hypothetical","abstention","en"]},
        {"id":"agentive_passive","inputs":"The bank was funded by a river association.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2_v02","agentive_relation","passive","negative_control","abstention","en"]},
        {"id":"open_set_marten","inputs":"The marten crossed the clearing.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2_v02","open_set","calibration","abstention","en"]},
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
        "dataset": "PLM-C2-v0.2-post-implementation-challenge",
        "schema_version": 2,
        "construction": "20 unseen semantic seeds x 3 deterministic wrappers",
        "limitations": [
            "Authored in the same development session; not an external corpus.",
            "The C2 v0.2 engine and Concept data were hashed before these seeds were authored.",
            "No engine or Concept-data tuning is permitted after the first evaluation run.",
            "Wrappers are dependent and must be cluster-bootstrapped by template_group.",
        ],
        "splits": {"dev": 0, "test": 60, "all": 60},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the frozen PLM-C2 v0.2 challenge set.")
    parser.add_argument("--out", default="data/challenge_c2_v02.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
