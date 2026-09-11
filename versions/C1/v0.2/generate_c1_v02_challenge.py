from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    """Unseen seeds authored only after the v0.2 engine was frozen."""
    return [
        {"id":"polarity_triple_en","inputs":"It is not impossible that this is not a dog.","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["challenge_v02","polarity","triple_negation","en"]},
        {"id":"polarity_denial_en","inputs":"The witness did not deny that it was a dog.","domain":"entity","expected":"DOG","tags":["challenge_v02","polarity","double_negation","en"]},
        {"id":"polarity_not_only_en","inputs":"It was not only a dog but also a cat.","domain":"entity","expected":"ANIMAL","tags":["challenge_v02","polarity","coordination","hierarchy","en"]},
        {"id":"polarity_triple_ja","inputs":"犬でないとは言えなくはない","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["challenge_v02","polarity","triple_negation","ja"]},
        {"id":"discourse_at_first_en","inputs":"At first it looked like a dog; in fact it was a cat.","domain":"entity","expected":"CAT","tags":["challenge_v02","discourse","correction","en"]},
        {"id":"discourse_final_sources","inputs":["Provisional finding: dog.","Final finding: cat."],"domain":"entity","expected":"CAT","tags":["challenge_v02","discourse","correction","source_order","en"]},
        {"id":"discourse_formerly_en","inputs":"Formerly classified as a dog; ultimately classified as a cat.","domain":"entity","expected":"CAT","tags":["challenge_v02","discourse","unseen_marker","en"]},
        {"id":"discourse_torikeshi_ja","inputs":"犬という判定を取り消し、猫と確定した","domain":"entity","expected":"CAT","tags":["challenge_v02","discourse","unseen_marker","ja"]},
        {"id":"morph_puppies_en","inputs":"The puppies were asleep.","domain":"entity","expected":"DOG","tags":["challenge_v02","morphology","irregular_plural","en"]},
        {"id":"morph_barked_en","inputs":"The animal barked twice.","domain":"action","expected":"BARK","tags":["challenge_v02","morphology","past_tense","en"]},
        {"id":"morph_banks_accounts_en","inputs":"The banks maintain customer accounts.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_v02","morphology","context_relation","en"]},
        {"id":"relation_follows_river_en","inputs":"The bank follows the river for several miles.","domain":"place","expected":"RIVER_BANK","tags":["challenge_v02","relation","spatial","en"]},
        {"id":"relation_water_policy_en","inputs":"The bank published a water policy.","domain":"place","expected":"UNRESOLVED","tags":["challenge_v02","relation","non_spatial","abstention","en"]},
        {"id":"relation_account_levels_en","inputs":"The bank keeps an account of river levels.","domain":"place","expected":"FINANCIAL_BANK","tags":["challenge_v02","relation","competing_context","en"]},
        {"id":"relation_hypothetical_ja","inputs":"もしbankのそばに川があれば避難する","domain":"place","expected":"UNRESOLVED","tags":["challenge_v02","relation","hypothetical","abstention","mixed"]},
        {"id":"relation_dry_riverbed_en","inputs":"The bank lies beside a dry riverbed.","domain":"place","expected":"RIVER_BANK","tags":["challenge_v02","relation","spatial","compound","en"]},
        {"id":"target_another_case_en","inputs":["A dog was logged.","In another case, a cat was logged."],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_v02","target_tracking","unseen_marker","abstention","en"]},
        {"id":"target_betsu_case_ja","inputs":["犬を記録した","別件では猫を記録した"],"domain":"entity","expected":"UNRESOLVED","tags":["challenge_v02","target_tracking","unseen_marker","abstention","ja"]},
        {"id":"target_afterward_places_en","inputs":["I opened an account at a bank.","Afterward I walked along a river bank."],"domain":"place","expected":"UNRESOLVED","tags":["challenge_v02","target_tracking","relation","abstention","en"]},
        {"id":"consensus_siblings_en","inputs":["One source says dog.","Another source says cat."],"domain":"entity","expected":"ANIMAL","tags":["challenge_v02","consensus","hierarchy","en"]},
    ]


def wrap(inputs, prefix):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}"
    return [f"{prefix}{value}" for value in inputs]


def build():
    semantic_seeds = seeds()
    if len(semantic_seeds) != 20:
        raise ValueError(f"Expected 20 seeds, got {len(semantic_seeds)}")
    wrappers = (("raw", ""), ("transcript", "Transcript: "), ("memo", "Memo: "))
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
        "dataset": "PLM-C1-v0.2-post-implementation-challenge",
        "schema_version": 2,
        "construction": "20 unseen semantic seeds x 3 deterministic wrappers",
        "limitations": [
            "Authored in the same development session; not an external corpus.",
            "The v0.2 engine was frozen before this file's first evaluation run.",
            "No engine or Concept-data tuning is permitted after the first run.",
            "Wrappers are dependent and must be cluster-bootstrapped by template_group.",
        ],
        "splits": {"dev": 0, "test": 60, "all": 60},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the frozen PLM-C1 v0.2 challenge set.")
    parser.add_argument("--out", default="data/challenge_c1_v02.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
