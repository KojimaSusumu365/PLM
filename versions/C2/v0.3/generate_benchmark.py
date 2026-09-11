from __future__ import annotations

import argparse
import json
from pathlib import Path


def seed_cases():
    return [
        {"id":"direct_dog_ja","inputs":"犬が走っている","domain":"entity","expected":"DOG","tags":["direct","ja"]},
        {"id":"direct_dog_alias_ja","inputs":"ワンちゃんが遊ぶ","domain":"entity","expected":"DOG","tags":["direct","ja"]},
        {"id":"direct_puppy_en","inputs":"A puppy is playing.","domain":"entity","expected":"DOG","tags":["direct","en"]},
        {"id":"direct_dog_en","inputs":"The dog waited.","domain":"entity","expected":"DOG","tags":["direct","en"]},
        {"id":"direct_cat_ja","inputs":"猫が眠っている","domain":"entity","expected":"CAT","tags":["direct","ja"]},
        {"id":"direct_cat_en","inputs":"The cat is sleeping.","domain":"entity","expected":"CAT","tags":["direct","en"]},
        {"id":"direct_human_ja","inputs":"その人が話した","domain":"entity","expected":"HUMAN","tags":["direct","ja"]},
        {"id":"direct_human_en","inputs":"A person arrived.","domain":"entity","expected":"HUMAN","tags":["direct","en"]},
        {"id":"direct_animal_ja","inputs":"動物がいる","domain":"entity","expected":"ANIMAL","tags":["direct","generic","ja"]},
        {"id":"direct_animal_en","inputs":"An animal moved.","domain":"entity","expected":"ANIMAL","tags":["direct","generic","en"]},
        {"id":"direct_living_ja","inputs":"未知の生物を観察した","domain":"entity","expected":"LIVING","tags":["direct","generic","ja"]},
        {"id":"direct_vehicle_ja","inputs":"自動車が止まった","domain":"entity","expected":"VEHICLE","tags":["direct","ja"]},
        {"id":"direct_vehicle_en","inputs":"The vehicle stopped.","domain":"entity","expected":"VEHICLE","tags":["direct","en"]},
        {"id":"direct_car_en","inputs":"A car stopped.","domain":"entity","expected":"VEHICLE","tags":["direct","en"]},
        {"id":"direct_bark_ja","inputs":"遠くで吠えている","domain":"action","expected":"BARK","tags":["direct","ja"]},
        {"id":"direct_bark_en","inputs":"Dogs bark loudly.","domain":"action","expected":"BARK","tags":["direct","en"]},
        {"id":"direct_bark_sound_ja","inputs":"キャンキャン聞こえた","domain":"action","expected":"BARK","tags":["direct","ja"]},
        {"id":"direct_vocalize_ja","inputs":"動物が鳴く","domain":"action","expected":"VOCALIZE","tags":["direct","generic","ja"]},
        {"id":"direct_vocalize_phrase_ja","inputs":"声を出した","domain":"action","expected":"VOCALIZE","tags":["direct","ja"]},
        {"id":"direct_vocalize_en","inputs":"An animal can vocalize.","domain":"action","expected":"VOCALIZE","tags":["direct","en"]},
        {"id":"direct_bite_ja","inputs":"犬が噛んだ","domain":"action","expected":"BITE","tags":["direct","ja"]},
        {"id":"direct_bite_en","inputs":"A dog can bite.","domain":"action","expected":"BITE","tags":["direct","en"]},
        {"id":"direct_financial_ja","inputs":"銀行へ行った","domain":"place","expected":"FINANCIAL_BANK","tags":["direct","ja"]},
        {"id":"direct_account_en","inputs":"The account was opened.","domain":"place","expected":"FINANCIAL_BANK","tags":["direct","en"]},
        {"id":"direct_loan_en","inputs":"The loan was approved.","domain":"place","expected":"FINANCIAL_BANK","tags":["direct","en"]},
        {"id":"direct_river_bank_ja","inputs":"川岸を歩いた","domain":"place","expected":"RIVER_BANK","tags":["direct","ja"]},
        {"id":"direct_river_bank_en","inputs":"We walked along the river bank.","domain":"place","expected":"RIVER_BANK","tags":["direct","en","overlap"]},

        {"id":"context_financial_money","inputs":"The bank handled money.","domain":"place","expected":"FINANCIAL_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_financial_deposit","inputs":"The bank accepted a deposit.","domain":"place","expected":"FINANCIAL_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_financial_account","inputs":"The bank maintains an account.","domain":"place","expected":"FINANCIAL_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_financial_loan","inputs":"The bank approved the loan.","domain":"place","expected":"FINANCIAL_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_river_water","inputs":"We sat on the bank beside water.","domain":"place","expected":"RIVER_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_river_shore","inputs":"The bank was close to the shore.","domain":"place","expected":"RIVER_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_river_flow","inputs":"The bank follows the river.","domain":"place","expected":"RIVER_BANK","tags":["ambiguity","context","en"]},
        {"id":"context_river_ja","inputs":"bankのそばを川が流れる","domain":"place","expected":"RIVER_BANK","tags":["ambiguity","context","mixed"]},

        {"id":"negated_dog_ja","inputs":"これは犬ではない","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["negation","contradiction","abstention","ja"]},
        {"id":"negated_dog_en","inputs":"This is not a dog.","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["negation","contradiction","abstention","en"]},
        {"id":"negated_cat_ja","inputs":"猫ではない","domain":"entity","expected":"UNRESOLVED","forbidden":["CAT"],"tags":["negation","contradiction","abstention","ja"]},
        {"id":"dog_not_cat_ja","inputs":"犬ではなく猫だった","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["negation","contradiction","ja"]},
        {"id":"dog_not_cat_en","inputs":"It was not a dog but a cat.","domain":"entity","expected":"CAT","forbidden":["DOG"],"tags":["negation","contradiction","en"]},
        {"id":"cat_negated_en","inputs":"A dog is not a cat.","domain":"entity","expected":"DOG","forbidden":["CAT"],"tags":["negation","contradiction","en"]},
        {"id":"negated_bank_en","inputs":"There is no bank here.","domain":"place","expected":"UNRESOLVED","forbidden":["FINANCIAL_BANK","RIVER_BANK"],"tags":["negation","contradiction","abstention","en"]},
        {"id":"negated_dog_casual_ja","inputs":"犬じゃなかった","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["negation","contradiction","abstention","ja"]},

        {"id":"hierarchy_dog","inputs":"この動物は犬です","domain":"entity","expected":"DOG","tags":["hierarchy","ja"]},
        {"id":"hierarchy_cat","inputs":"この動物は猫です","domain":"entity","expected":"CAT","tags":["hierarchy","ja"]},
        {"id":"hierarchy_human","inputs":"この動物は人です","domain":"entity","expected":"HUMAN","tags":["hierarchy","ja"]},
        {"id":"hierarchy_animal","inputs":"この生物は動物です","domain":"entity","expected":"ANIMAL","tags":["hierarchy","ja"]},
        {"id":"hierarchy_bark","inputs":"声を出して吠えた","domain":"action","expected":"BARK","tags":["hierarchy","ja"]},

        {"id":"abstain_bare_bank","inputs":"bank","domain":"place","expected":"UNRESOLVED","tags":["ambiguity","abstention","en"]},
        {"id":"abstain_unknown","inputs":"量子もつれについて考える","domain":"entity","expected":"UNRESOLVED","tags":["unknown","abstention","ja"]},
        {"id":"conflict_sibling_parent","inputs":["犬がいる","猫がいる"],"domain":"entity","expected":"ANIMAL","tags":["conflict","hierarchy","ja"]},
        {"id":"conflict_bank_balanced","inputs":["The bank handled money.","We sat on the bank beside water."],"domain":"place","expected":"UNRESOLVED","tags":["conflict","ambiguity","abstention","en"]},
        {"id":"conflict_action_balanced","inputs":["吠えた","噛んだ"],"domain":"action","expected":"UNRESOLVED","tags":["conflict","abstention","ja"]},

        {"id":"minority_financial","inputs":["bank","bank","The bank accepted my money."],"domain":"place","expected":"FINANCIAL_BANK","tags":["minority_evidence","ambiguity","context","en"]},
        {"id":"minority_river","inputs":["bank","bank","The bank was beside water."],"domain":"place","expected":"RIVER_BANK","tags":["minority_evidence","ambiguity","context","en"]},
        {"id":"minority_specific_entity","inputs":["動物です","犬です"],"domain":"entity","expected":"DOG","tags":["minority_evidence","hierarchy","ja"]},
        {"id":"minority_specific_action","inputs":["鳴く","吠えた"],"domain":"action","expected":"BARK","tags":["minority_evidence","hierarchy","ja"]},

        {"id":"boundary_scar","inputs":"Scar tissue formed.","domain":"entity","expected":"UNRESOLVED","forbidden":["VEHICLE"],"tags":["hard_negative","boundary","abstention","en"]},
        {"id":"boundary_hotdog","inputs":"The hotdog stand closed.","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["hard_negative","boundary","abstention","en"]},
        {"id":"boundary_humanity","inputs":"Humanity is a broad idea.","domain":"entity","expected":"UNRESOLVED","forbidden":["HUMAN"],"tags":["hard_negative","boundary","abstention","en"]}
        ,
        {"id":"stress_correction_ja","inputs":"犬だと思ったが、実際は猫だった","domain":"entity","expected":"CAT","tags":["stress","correction","long_scope","ja"]},
        {"id":"stress_correction_en","inputs":"It looked like a dog, but the final identification was a cat.","domain":"entity","expected":"CAT","tags":["stress","correction","long_scope","en"]},
        {"id":"stress_long_negation_en","inputs":"It is not really very clearly a dog.","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["stress","negation","long_scope","abstention","en"]},
        {"id":"stress_discontinuous_negation_en","inputs":"The dog did not, despite appearances, bark.","domain":"action","expected":"UNRESOLVED","forbidden":["BARK"],"tags":["stress","negation","long_scope","abstention","en"]},
        {"id":"stress_predicate_negation_ja","inputs":"犬は吠えなかった","domain":"action","expected":"UNRESOLVED","forbidden":["BARK"],"tags":["stress","negation","predicate","abstention","ja"]},
        {"id":"stress_cross_input_context","inputs":["The bank was mentioned.","Separately, water spilled."],"domain":"place","expected":"UNRESOLVED","tags":["stress","context_scope","abstention","en"]},
        {"id":"stress_unrelated_clause_context","inputs":"The bank was discussed while water spilled from a glass.","domain":"place","expected":"UNRESOLVED","tags":["stress","context_scope","abstention","en"]},
        {"id":"stress_negated_context","inputs":"The bank has no water nearby.","domain":"place","expected":"UNRESOLVED","tags":["stress","context_scope","negation","abstention","en"]},
        {"id":"stress_financial_negative_affordance","inputs":"The bank does not offer loans.","domain":"place","expected":"FINANCIAL_BANK","tags":["stress","context_scope","negation","en"]},
        {"id":"stress_two_places","inputs":["I visited a bank.","Later I crossed a river."],"domain":"place","expected":"UNRESOLVED","tags":["stress","conflict","context_scope","abstention","en"]},
        {"id":"stress_ordered_correction","inputs":["犬だ","犬らしい","訂正すると猫だった"],"domain":"entity","expected":"CAT","tags":["stress","correction","order_sensitive","ja"]},
        {"id":"stress_complex_negation_ja","inputs":"犬というわけではない","domain":"entity","expected":"UNRESOLVED","forbidden":["DOG"],"tags":["stress","negation","long_scope","abstention","ja"]}
    ]


def wrap_inputs(inputs, prefix: str, suffix: str):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}{suffix}"
    return [f"{prefix}{text}{suffix}" for text in inputs]


def build_dataset():
    seeds = seed_cases()
    if len(seeds) != 72:
        raise ValueError(f"Expected 72 semantic seeds, got {len(seeds)}")
    variants = [
        ("dev", "dev", "", ""),
        ("test_a", "test", "記録: ", ""),
        ("test_b", "test", "観察結果 — ", ""),
        ("test_c", "test", "Context: ", ""),
    ]
    cases = []
    for seed in seeds:
        for variant, split, prefix, suffix in variants:
            row = dict(seed)
            row["id"] = f"{seed['id']}__{variant}"
            row["template_group"] = seed["id"]
            row["split"] = split
            row["inputs"] = wrap_inputs(seed["inputs"], prefix, suffix)
            row["tags"] = sorted(set(seed.get("tags", []) + [split]))
            cases.append(row)
    return {
        "dataset": "PLM-C0-v0.3-benchmark",
        "schema_version": 2,
        "construction": "72 semantic seeds x 4 deterministic surface wrappers",
        "limitations": [
            "Templated, closed-vocabulary functional benchmark; not an external corpus.",
            "Dev and test share semantic seeds but use different wrappers.",
            "Repeated wrappers must be cluster-bootstrapped by template_group.",
            "The stress subset intentionally includes unsupported discourse and scope phenomena.",
        ],
        "splits": {"dev": 72, "test": 216, "all": 288},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the deterministic PLM-C0 v0.3 benchmark.")
    parser.add_argument("--out", default="data/benchmark_v03.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
