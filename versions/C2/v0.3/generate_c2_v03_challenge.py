from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    """Unseen seeds authored only after the C2 v0.3 engine was frozen."""
    return [
        {"id":"revision_recategorized","inputs":"Originally marked dog: recategorized as cat.","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","revision_role","en"]},
        {"id":"revision_redesignated","inputs":"At the outset it was dog: redesignated as cat.","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","revision_role","en"]},
        {"id":"revision_changed_classification","inputs":"Originally it was dog. Changed the classification to cat.","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","revision_role","sentence_boundary","en"]},
        {"id":"revision_japanese_name_change","inputs":"当初は犬。名称変更で猫。","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","revision_role","ja"]},
        {"id":"revision_reidentified","inputs":"Originally marked dog: reidentified as cat.","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","revision_role","unseen_predicate","en"]},
        {"id":"reference_later_one","inputs":["A dog and a cat were registered.","The later one was chosen."],"domain":"entity","expected":"CAT","tags":["challenge_c2_v03","coreference","nominal_reference","en"]},
        {"id":"reference_previous_one","inputs":["A cat and a dog were registered.","The previous one was chosen."],"domain":"entity","expected":"DOG","tags":["challenge_c2_v03","coreference","nominal_reference","en"]},
        {"id":"reference_single_it","inputs":["A cat entered the room.","It was photographed."],"domain":"entity","expected":"CAT","tags":["challenge_c2_v03","coreference","pronoun","en"]},
        {"id":"reference_ambiguous_it","inputs":["A dog and a cat entered the room.","It was photographed."],"domain":"entity","expected":"ANIMAL","tags":["challenge_c2_v03","coreference","ambiguity_guard","en"]},
        {"id":"reference_plural_they","inputs":["A dog and a cat entered the room.","They were photographed."],"domain":"entity","expected":"ANIMAL","tags":["challenge_c2_v03","coreference","plural","en"]},
        {"id":"reference_japanese_former","inputs":["犬と猫を登録した。","前者を選んだ。"],"domain":"entity","expected":"DOG","tags":["challenge_c2_v03","coreference","ja"]},
        {"id":"reference_japanese_sore","inputs":["猫を登録した。","それを選んだ。"],"domain":"entity","expected":"CAT","tags":["challenge_c2_v03","coreference","pronoun","ja"]},
        {"id":"role_awarded","inputs":"The bank awarded grants for a river restoration.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v03","relation_frame","role_affordance","en"]},
        {"id":"role_donated","inputs":"The bank donated equipment to a river cleanup.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v03","relation_frame","role_affordance","en"]},
        {"id":"role_subsidized","inputs":"The bank subsidized research on river pollution.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_c2_v03","relation_frame","role_affordance","en"]},
        {"id":"role_negated_backed","inputs":"The bank never backed a river conservation plan.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2_v03","relation_frame","negation","abstention","en"]},
        {"id":"role_hypothetical_invested","inputs":"If the bank invested in a river project, it would disclose it.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2_v03","relation_frame","hypothetical","abstention","en"]},
        {"id":"role_passive_backed","inputs":"The bank was backed by a river association.","domain":"place","expected":"UNRESOLVED","tags":["challenge_c2_v03","relation_frame","passive","abstention","en"]},
        {"id":"role_noun_support_structure","inputs":"The bank support structure stands near the river.","domain":"place","expected":"RIVER_BANK","tags":["challenge_c2_v03","relation_frame","part_of_speech","adversarial","en"]},
        {"id":"correction_japanese_mushiro","inputs":"犬、むしろ、猫。","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","correction_scope","ja"]},
        {"id":"correction_japanese_tadashiku","inputs":"犬、正しくは、猫。","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","correction_scope","ja"]},
        {"id":"correction_english_instead","inputs":"The record said dog, instead cat.","domain":"entity","expected":"CAT","tags":["challenge_c2_v03","correction_scope","en"]},
        {"id":"open_set_badger","inputs":"A badger crossed the field.","domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2_v03","open_set","calibration","abstention","en"]},
        {"id":"temporal_distinct_subjects","inputs":["A dog was recorded.","Thereafter, a cat was recorded."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_c2_v03","temporal_relation","abstention","en"]},
    ]


def wrap(inputs, prefix):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}"
    return [f"{prefix}{value}" for value in inputs]


def build():
    semantic_seeds = seeds()
    if len(semantic_seeds) != 24:
        raise ValueError(f"Expected 24 seeds, got {len(semantic_seeds)}")
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
        "dataset": "PLM-C2-v0.3-post-implementation-challenge",
        "schema_version": 2,
        "construction": "24 unseen semantic seeds x 3 deterministic wrappers",
        "limitations": [
            "Authored in the same development session; not an external corpus.",
            "The C2 v0.3 engine and Concept data were hashed before these seeds were authored.",
            "No engine or Concept-data tuning is permitted after the first evaluation run.",
            "Wrappers are dependent and must be cluster-bootstrapped by template_group.",
        ],
        "splits": {"dev": 0, "test": 72, "all": 72},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the frozen PLM-C2 v0.3 challenge set.")
    parser.add_argument("--out", default="data/challenge_c2_v03.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
