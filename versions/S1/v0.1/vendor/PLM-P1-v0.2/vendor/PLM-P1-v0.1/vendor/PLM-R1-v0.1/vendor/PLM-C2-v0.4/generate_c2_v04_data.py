"""Specification-derived fixtures; no engine import, no wrapper expansion.

All sets were authored by the implementing assistant. A held-out execution split
does NOT constitute an independently authored or externally validated benchmark.
"""
import json
from pathlib import Path


def financial(predicate, obj, voice="active", polarity="positive", modality="asserted", applied=True):
    return dict(relation_type="FINANCIAL_AFFORDANCE", subject="bank", predicate=predicate,
                object_text=obj, voice=voice, polarity=polarity, modality=modality, applied=applied)


def reference(concept, ordinal=0):
    return dict(relation_type="COREFERENCE", predicate="REFERS_TO", target_concept=concept,
                antecedent_ordinal=ordinal, polarity="positive", applied=True)


def revision(target_text):
    return dict(relation_type="REVISION", predicate="REVISES", target_text=target_text,
                polarity="positive", modality="corrective", applied=True)


def spatial(connector_object="river"):
    return dict(relation_type="SPATIAL_ASSOCIATION", subject="bank", predicate="LOCATED_NEAR",
                object_text=connector_object, polarity="positive", applied=True)


def case(name, inputs, expected, gold=(), domain="place", **extra):
    return dict(id=name, template_group=name, inputs=inputs, expected=expected, domain=domain,
                gold_frames=list(gold), tags=["v04_semantic"], **extra)


def development():
    return [
        case("dev_award_active", "The bank awarded grants for a river restoration.", "FINANCIAL_BANK", [financial("award", "grants for a river restoration")]),
        case("dev_award_passive", "Grants for a river restoration were awarded by the bank.", "FINANCIAL_BANK", [financial("award", "grants for a river restoration", "passive")]),
        case("dev_negation", "The bank did not award grants for a river restoration.", "UNRESOLVED", [financial("award", "grants for a river restoration", polarity="negative", applied=False)]),
        case("dev_hypothetical", "If the bank awarded grants for a river restoration, it would report it.", "UNRESOLVED", [financial("award", "grants for a river restoration", modality="hypothetical", applied=False)]),
        case("dev_patient", "The bank was supported by a river alliance.", "UNRESOLVED"),
        case("dev_noun", "The bank support structure stands near the river.", "RIVER_BANK", [spatial()]),
        case("dev_physical_support", "The bank supports a wooden bridge.", "UNRESOLVED"),
        case("dev_funded_passive", "Research on a river was funded by the bank.", "FINANCIAL_BANK", [financial("fund", "research on a river", "passive")]),
        case("dev_near", "The bank is near the river.", "RIVER_BANK", [spatial()]),
        case("dev_unsupported_finance_context", "The bank has a loan account.", "FINANCIAL_BANK"),
        case("dev_two_dogs_it", ["A dog and another dog entered.", "It was photographed."], "DOG", domain="entity", reference_status="ambiguous", distinct_nominal_entities=2),
        case("dev_two_dogs_they", ["A dog and another dog entered.", "They were photographed."], "DOG", [reference("DOG", 0), reference("DOG", 1)], "entity", reference_status="resolved", distinct_nominal_entities=2),
        case("dev_single_it", ["A cat arrived.", "It was photographed."], "CAT", [reference("CAT")], "entity", reference_status="resolved"),
        case("dev_former_same", ["A dog and another dog entered.", "The former was selected."], "DOG", [reference("DOG", 0)], "entity"),
        case("dev_latter_mixed", ["A dog and a cat entered.", "The later one was selected."], "CAT", [reference("CAT", 1)], "entity"),
        case("dev_group_singular", ["Two dogs entered.", "It was photographed."], "DOG", domain="entity", reference_status="ambiguous"),
        case("dev_group_plural", ["Two cats entered.", "They were photographed."], "CAT", [reference("CAT")], "entity"),
        case("dev_japanese_revision", "犬、いや、猫。", "CAT", [revision("犬")], "entity"),
        case("dev_reidentified", "Originally marked dog: reidentified as cat.", "CAT", [revision("Originally marked dog")], "entity"),
        case("dev_no_revision_target", "Reclassified as cat.", "CAT", domain="entity"),
        case("dev_unknown", "A badger crossed the field.", "UNRESOLVED", domain="entity"),
        case("dev_empty", "", "UNRESOLVED", domain="entity"),
        case("dev_quoted", 'The report says "the bank awarded grants for a river restoration".', "FINANCIAL_BANK"),
    ]


def calibration():
    # Calibrator-only data, not used for implementation acceptance or final scoring.
    values = [
        ("A puppy slept.", "DOG", "entity"), ("A human walked.", "HUMAN", "entity"),
        ("A vehicle stopped.", "VEHICLE", "entity"), ("An animal rested.", "ANIMAL", "entity"),
        ("A cat slept.", "CAT", "entity"), ("A dog slept.", "DOG", "entity"),
        ("A marten appeared.", "UNRESOLVED", "entity"), ("Nothing relevant was recorded.", "UNRESOLVED", "entity"),
        ("A dog and a cat slept.", "ANIMAL", "entity"),
        (["A dog and a cat slept.", "It was selected."], "ANIMAL", "entity"),
        (["A cat and another cat slept.", "It was selected."], "CAT", "entity"),
        (["A dog and a cat slept.", "The latter was selected."], "CAT", "entity"),
        ("The bank granted aid for river research.", "FINANCIAL_BANK", "place"),
        ("Aid for river research was granted by the bank.", "FINANCIAL_BANK", "place"),
        ("The bank invested in a river project.", "FINANCIAL_BANK", "place"),
        ("The bank financed a river study.", "FINANCIAL_BANK", "place"),
        ("The bank was financed by a river association.", "UNRESOLVED", "place"),
        ("The bank did not fund a river study.", "UNRESOLVED", "place"),
        ("The bank is beside the river.", "RIVER_BANK", "place"),
        ("A river bank collapsed.", "RIVER_BANK", "place"),
        ("A bank lies near water.", "RIVER_BANK", "place"),
        ("The bank disbursed aid for river research.", "FINANCIAL_BANK", "place"),
        ("Originally called cat: reassessed as dog.", "DOG", "entity"),
        (["A dog and a cat slept.", "The feline was selected."], "CAT", "entity"),
        ("The bank supports an old wall.", "UNRESOLVED", "place"),
        ("犬、正しくは、猫。", "CAT", "entity"),
        ("猫、いや、犬。", "DOG", "entity"),
        ("The bank donated equipment to river research.", "FINANCIAL_BANK", "place"),
        ("The bank sponsored river research.", "FINANCIAL_BANK", "place"),
        ("A dog was recorded. Later a cat was recorded.", "UNRESOLVED", "entity"),
    ]
    return [case(f"cal_{i:03d}", text, expected, domain=domain) for i, (text, expected, domain) in enumerate(values, 1)]


def holdout():
    return [
        case("test_donate_perfect", "Equipment for river research has been donated by the bank.", "FINANCIAL_BANK", [financial("donate", "equipment for river research", "passive")]),
        case("test_subsidize", "The bank subsidized a river cleanup program.", "FINANCIAL_BANK", [financial("subsidize", "a river cleanup program")]),
        case("test_subsidize_passive", "A river cleanup program was subsidized by the bank.", "FINANCIAL_BANK", [financial("subsidize", "a river cleanup program", "passive")]),
        case("test_adverb", "The bank regularly supports river conservation projects.", "FINANCIAL_BANK", [financial("support", "river conservation projects")]),
        case("test_progressive", "The bank is allocating resources to river research.", "FINANCIAL_BANK", [financial("allocate", "resources to river research")]),
        case("test_negative_passive", "Aid for river restoration was not granted by the bank.", "UNRESOLVED", [financial("grant", "aid for river restoration", "passive", "negative", applied=False)]),
        case("test_contracted_negation", "The bank didn't support a river research project.", "UNRESOLVED", [financial("support", "a river research project", polarity="negative", applied=False)]),
        case("test_conditional_passive", "River research might be funded by the bank.", "UNRESOLVED", [financial("fund", "river research", "passive", modality="hypothetical", applied=False)]),
        case("test_patient_role", "The bank was awarded by a river association.", "UNRESOLVED"),
        case("test_noun_structure", "The bank support frame is beside the river.", "RIVER_BANK", [spatial()]),
        case("test_water", "The bank stands near the water.", "RIVER_BANK", [spatial("water")]),
        case("test_passive_agent_manager", "A river plan was supported by the bank manager.", "UNRESOLVED"),
        case("test_disbursed", "The bank disbursed grants for river restoration.", "FINANCIAL_BANK", [financial("disburse", "grants for river restoration")]),
        case("test_nominal_finance", "The bank account was reviewed.", "FINANCIAL_BANK"),
        case("test_irrelevant_sentence", "The sky was clear. The bank backed river restoration plans.", "FINANCIAL_BANK", [financial("back", "river restoration plans")]),
        case("test_record_prefix", "Record: A river study was financed by the bank.", "FINANCIAL_BANK", [financial("finance", "a river study", "passive")]),
        case("test_two_cats_it", ["A cat and another cat arrived.", "It was examined."], "CAT", domain="entity", reference_status="ambiguous", distinct_nominal_entities=2),
        case("test_two_cats_they", ["A cat and another cat arrived.", "They were examined."], "CAT", [reference("CAT", 0), reference("CAT", 1)], "entity", reference_status="resolved", distinct_nominal_entities=2),
        case("test_same_type_latter", ["A cat and another cat arrived.", "The latter was selected."], "CAT", [reference("CAT", 1)], "entity"),
        case("test_order_swapped", ["A cat and a dog were registered.", "The earlier one was chosen."], "CAT", [reference("CAT", 0)], "entity"),
        case("test_group_ambiguous", ["Three cats arrived.", "It was examined."], "CAT", domain="entity", reference_status="ambiguous"),
        case("test_plural_group", ["Several dogs arrived.", "They were examined."], "DOG", [reference("DOG")], "entity"),
        case("test_japanese_same", ["猫と別の猫を登録した。", "それを選んだ。"], "CAT", domain="entity", reference_status="ambiguous", distinct_nominal_entities=2),
        case("test_japanese_latter", ["猫と犬を登録した。", "後者を選んだ。"], "DOG", [reference("DOG", 1)], "entity"),
        case("test_reference_noise", ["A cat arrived.", "The weather was calm.", "It was examined."], "CAT", [reference("CAT")], "entity"),
        case("test_no_antecedent", "It was examined.", "UNRESOLVED", domain="entity", reference_status="unresolved"),
        case("test_japanese_reverse_revision", "猫、正しくは、犬。", "DOG", [revision("猫")], "entity"),
        case("test_revision_period", "Initially recorded as cat. Reidentified as dog.", "DOG", [revision("Initially recorded as cat")], "entity"),
        case("test_no_correction_target", "Reidentified as dog.", "DOG", domain="entity"),
        case("test_unregistered_predicate", "Originally marked cat: reassessed as dog.", "DOG", [revision("Originally marked cat")], "entity"),
        case("test_new_species", "An otter crossed the path.", "UNRESOLVED", domain="entity"),
        case("test_empty_list", [], "UNRESOLVED", domain="entity"),
    ]


def metamorphic():
    pairs = []
    for i, (verb, past, obj) in enumerate([
        ("grant", "granted", "aid for a river project"),
        ("award", "awarded", "grants for river research"),
        ("fund", "funded", "a river conservation study"),
        ("donate", "donated", "equipment for river cleanup"),
        ("support", "supported", "a river restoration plan"),
        ("finance", "financed", "a river research program"),
    ], 1):
        pairs.append({"id": f"voice_{i}", "relation": "voice_invariance",
                      "a": f"The bank {past} {obj}.", "b": f"{obj.capitalize()} was {past} by the bank.",
                      "expected": "FINANCIAL_BANK", "predicate": verb, "object_text": obj})
    pairs.extend([
        {"id": "prefix", "relation": "noise_invariance", "a": "The bank granted aid for river research.", "b": "Observation: The bank granted aid for river research.", "expected": "FINANCIAL_BANK"},
        {"id": "sentence_noise", "relation": "noise_invariance", "a": "The bank funded river research.", "b": "The sky is clear. The bank funded river research.", "expected": "FINANCIAL_BANK"},
        {"id": "negation", "relation": "polarity_flip", "a": "The bank awarded grants for river research.", "b": "The bank did not award grants for river research.", "expected": "FINANCIAL_BANK", "expected_b": "UNRESOLVED"},
    ])
    return pairs


def main():
    root = Path(__file__).resolve().parent / "data"
    for split, cases in (("development", development()), ("calibration", calibration()), ("holdout", holdout())):
        for c in cases:
            c["split"] = split
        dataset = {"dataset": f"PLM-C2-v0.4-{split}", "schema_version": 3,
                   "independent_authorship": False, "external_corpus": False,
                   "construction": "semantic fixtures; no dependent wrapper expansion", "cases": cases}
        (root / f"{split}_c2_v04.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "metamorphic_c2_v04.json").write_text(json.dumps(metamorphic(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Generated development, calibration, holdout, and metamorphic specifications.")


if __name__ == "__main__":
    main()
