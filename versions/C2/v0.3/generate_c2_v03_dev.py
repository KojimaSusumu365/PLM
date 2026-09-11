from __future__ import annotations

import argparse
import json
from pathlib import Path


def seeds():
    return [
        {"id":"dev_revision_reclassified","inputs":"Originally marked dog: reclassified as cat.","domain":"entity","expected":"CAT","tags":["development_c2_v03","revision_role","en"]},
        {"id":"dev_revision_relabeled","inputs":"Originally marked dog: relabeled as cat.","domain":"entity","expected":"CAT","tags":["development_c2_v03","revision_role","en"]},
        {"id":"dev_reference_earlier","inputs":["A dog and a cat were listed.","The earlier one was selected."],"domain":"entity","expected":"DOG","tags":["development_c2_v03","extended_reference","en"]},
        {"id":"dev_reference_previous","inputs":["A dog and a cat were listed.","The previous one was selected."],"domain":"entity","expected":"CAT","tags":["development_c2_v03","extended_reference","en"]},
        {"id":"dev_reference_japanese_latter","inputs":["犬と猫を記録した。","後者を選んだ。"],"domain":"entity","expected":"CAT","tags":["development_c2_v03","extended_reference","ja"]},
        {"id":"dev_japanese_correction","inputs":"犬、いや、猫。","domain":"entity","expected":"CAT","tags":["development_c2_v03","correction_scope","ja"]},
        {"id":"dev_japanese_revision","inputs":"当初は犬：再分類すると猫。","domain":"entity","expected":"CAT","tags":["development_c2_v03","revision_role","ja"]},
        {"id":"dev_role_granted","inputs":"The bank granted aid to a river project.","domain":"place","expected":"FINANCIAL_BANK","tags":["development_c2_v03","role_affordance","en"]},
        {"id":"dev_role_allocated","inputs":"The bank allocated resources to river research.","domain":"place","expected":"FINANCIAL_BANK","tags":["development_c2_v03","role_affordance","en"]},
        {"id":"dev_role_passive","inputs":"The bank was supported by a river alliance.","domain":"place","expected":"UNRESOLVED","tags":["development_c2_v03","role_affordance","passive","en"]},
    ]


def wrap(inputs, prefix):
    if isinstance(inputs, str):
        return f"{prefix}{inputs}"
    return [f"{prefix}{value}" for value in inputs]


def build():
    wrappers = (("raw", ""), ("record", "Record: "), ("observation", "Observation: "))
    cases = []
    for seed in seeds():
        for variant, prefix in wrappers:
            case = dict(seed)
            case["id"] = f"{seed['id']}__{variant}"
            case["template_group"] = seed["id"]
            case["split"] = "dev"
            case["inputs"] = wrap(seed["inputs"], prefix)
            case["tags"] = sorted(set(seed["tags"] + ["dev"]))
            cases.append(case)
    return {
        "dataset": "PLM-C2-v0.3-development-diagnostic",
        "schema_version": 2,
        "construction": "10 development semantic seeds x 3 deterministic wrappers",
        "splits": {"dev": 30, "test": 0, "all": 30},
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate the PLM-C2 v0.3 development set.")
    parser.add_argument("--out", default="data/development_c2_v03.json")
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = build()
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(dataset['cases'])} cases to {output.resolve()}")


if __name__ == "__main__":
    main()
