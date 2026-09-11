from copy import deepcopy
from pathlib import Path
import json
import unittest

from plm_c0 import evaluate, load_cases
from plm_c2 import C2Config, PLMC2Engine, audit_result, export_r1_observations
from plm_c2.audit import validate_schema
from plm_c2.calibration import fit_isotonic, fit_calibration
from plm_c2.evaluation import ROOT, load_v04_cases, semantic_evaluate, metamorphic_evaluate, verify_freeze


class TestSemanticRoles(unittest.TestCase):
    def setUp(self):
        self.engine = PLMC2Engine()

    def test_01_noun_is_not_a_financial_action(self):
        r = self.engine.analyze("The bank support structure stands near the river.")
        self.assertEqual(r["selections"]["place"]["selected"], "RIVER_BANK")
        self.assertFalse(any(f["relation_type"] == "FINANCIAL_AFFORDANCE" for f in r["relation_frames"]))

    def test_02_active_passive_preserve_roles(self):
        for text, voice in (("The bank awarded grants for a river restoration.", "active"),
                            ("Grants for a river restoration were awarded by the bank.", "passive")):
            r = self.engine.analyze(text)
            self.assertEqual(r["selections"]["place"]["selected"], "FINANCIAL_BANK")
            f = next(f for f in r["relation_frames"] if f["extraction_rule"] == "bounded_bank_event")
            self.assertEqual((f["subject"], f["predicate"], f["voice"]), ("bank", "award", voice))
            self.assertEqual(f["object_text"].lower(), "grants for a river restoration")
            self.assertEqual(f["semantic_status"], "rule_checked")

    def test_03_bank_patient_is_not_bank_agent(self):
        r = self.engine.analyze("The bank was supported by a river alliance.")
        self.assertEqual(r["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertFalse(any(f["applied"] for f in r["relation_frames"]))

    def test_04_negation_preserved(self):
        r = self.engine.analyze("The bank did not award grants for a river restoration.")
        f = next(f for f in r["relation_frames"] if f["extraction_rule"] == "bounded_bank_event")
        self.assertEqual(f["polarity"], "negative")
        self.assertFalse(f["applied"])
        self.assertEqual(r["r1_boundary"]["positive_rule_checked_frame_ids"], [])

    def test_05_hypothetical_object_ends_at_main_clause(self):
        r = self.engine.analyze("If the bank awarded grants for a river restoration, it would report it.")
        f = next(f for f in r["relation_frames"] if f["extraction_rule"] == "bounded_bank_event")
        self.assertEqual(f["object_text"], "grants for a river restoration")
        self.assertEqual(f["modality"], "hypothetical")
        self.assertFalse(f["applied"])

    def test_06_physical_support_requires_review(self):
        r = self.engine.analyze("The bank supports a wooden bridge.")
        self.assertTrue(all(f["semantic_status"] == "quarantined" for f in r["relation_frames"]))

    def test_07_argument_and_nominal_share_entity(self):
        r = self.engine.analyze("The bank granted aid to a river project.")
        bank_mentions = [m for m in r["mentions"] if m["span"]["text"] == "bank"]
        self.assertEqual(len({m["entity_id"] for m in bank_mentions}), 1)

    def test_08_every_mention_is_anchored(self):
        for c in load_v04_cases("development"):
            r = self.engine.analyze(c["inputs"])
            self.assertTrue(r["semantic_audit"]["schema_valid"], c["id"])
            self.assertTrue(r["semantic_audit"]["graph_valid"], c["id"])


class TestInstanceAndRevision(unittest.TestCase):
    def test_09_same_concept_distinct_individuals(self):
        r = PLMC2Engine().analyze(["A dog and another dog entered.", "It was photographed."])
        dogs = [m for m in r["mentions"] if m["kind"] == "nominal" and "DOG" in m["concept_candidates"]]
        self.assertEqual(len({m["entity_id"] for m in dogs}), 2)
        self.assertNotEqual(dogs[0]["evidence_ids"], dogs[1]["evidence_ids"])
        self.assertEqual(r["reference_links"], [])
        self.assertEqual(r["reference_resolutions"][0]["status"], "ambiguous")

    def test_10_plural_preserves_both_instances_without_double_vote(self):
        r = PLMC2Engine().analyze(["A dog and another dog entered.", "They were photographed."])
        self.assertEqual(len({x["antecedent_entity_id"] for x in r["reference_links"]}), 2)
        self.assertEqual(sum(e["reason"] == "instance coreference" for e in r["evidence"]), 1)
        self.assertEqual(len({x["antecedent_evidence_id"] for x in r["reference_links"]}), 2)

    def test_11_former_and_latter_same_species(self):
        ids = []
        for cue in ("former", "latter"):
            r = PLMC2Engine().analyze(["A dog and another dog entered.", f"The {cue} was selected."])
            ids.append(r["reference_links"][0]["antecedent_mention_id"])
        self.assertNotEqual(ids[0], ids[1])

    def test_12_group_cannot_license_singular(self):
        r = PLMC2Engine().analyze(["Two dogs entered.", "It was photographed."])
        self.assertEqual(r["reference_links"], [])
        self.assertEqual(r["reference_resolutions"][0]["status"], "ambiguous")

    def test_13_later_one_is_not_a_new_event(self):
        r = PLMC2Engine().analyze(["A dog and a cat entered.", "The later one was selected."])
        self.assertEqual(r["selections"]["entity"]["selected"], "CAT")

    def test_14_inactive_antecedent_not_revived(self):
        r = PLMC2Engine().analyze(["Originally marked dog: reclassified as cat.", "It was selected."])
        self.assertEqual({x["concept"] for x in r["reference_links"]}, {"CAT"})

    def test_15_japanese_correction_targets_actual_evidence(self):
        r = PLMC2Engine().analyze("犬、いや、猫。")
        frames = [f for f in r["relation_frames"] if f["relation_type"] == "REVISION"]
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]["object_text"], "犬")
        self.assertEqual(frames[0]["target_clause_id"], "S001:C001")

    def test_16_no_prior_evidence_no_revision_edge(self):
        r = PLMC2Engine().analyze("Reidentified as cat.")
        self.assertEqual(r["relation_frames"], [])

    def test_17_reidentified_known_gap_fixed(self):
        r = PLMC2Engine().analyze("Originally marked dog: reidentified as cat.")
        self.assertEqual(r["selections"]["entity"]["selected"], "CAT")
        self.assertEqual(r["semantic_audit"]["rule_checked_count"], 1)

    def test_18_state_does_not_leak_between_analyses(self):
        engine = PLMC2Engine()
        engine.analyze(["A dog entered.", "It was selected."])
        r = engine.analyze("It was selected.")
        self.assertEqual(r["reference_links"], [])


class TestBoundary(unittest.TestCase):
    def sample(self):
        return PLMC2Engine().analyze("The bank granted aid to a river project.")

    def test_19_observe_only_and_stable_namespacing(self):
        a, b = export_r1_observations(self.sample()), export_r1_observations(self.sample())
        self.assertEqual(a, b)
        self.assertFalse(a["boundary"]["inference_enabled"])
        self.assertTrue(all(not x["eligible_for_inference"] for x in a["observations"]))

    def test_20_inference_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            export_r1_observations(self.sample(), mode="infer")

    def test_21_empty_not_ready(self):
        for text in ("", [], "A badger crossed the field."):
            r = PLMC2Engine().analyze(text)
            self.assertFalse(r["relation_contract"]["observation_ready"])
            self.assertFalse(r["relation_contract"]["inference_ready"])

    def test_22_bad_schema_rejected_even_with_cached_pass(self):
        r = self.sample()
        r["relation_frames"][0]["applied"] = "true"
        with self.assertRaises(ValueError):
            export_r1_observations(r)

    def test_23_dangling_graph_edge_rejected(self):
        r = self.sample()
        r["claim_graph"]["edges"][0]["target"] = "missing"
        with self.assertRaises(ValueError):
            export_r1_observations(r)

    def test_24_wrong_subject_quarantined(self):
        r = self.sample()
        f = next(f for f in r["relation_frames"] if f["extraction_rule"] == "bounded_bank_event")
        f["subject"] = "river"
        out = export_r1_observations(r)
        self.assertEqual(next(x for x in out["observations"] if x["frame_id"] == f["frame_id"])["semantic_status"], "quarantined")

    def test_25_bad_source_span_rejected(self):
        r = self.sample()
        r["mentions"][0]["span"]["text"] = "wrong"
        with self.assertRaises(ValueError):
            export_r1_observations(r)

    def test_26_unverified_legacy_relation_not_promoted(self):
        r = PLMC2Engine().analyze("The bank has a loan account.")
        self.assertTrue(r["relation_frames"])
        self.assertEqual(r["semantic_audit"]["rule_checked_count"], 0)
        self.assertFalse(r["r1_boundary"]["observation_ready"])

    def test_27_schema_checks_types_enums_and_additional_fields(self):
        f = self.sample()["relation_frames"][0]
        self.assertEqual(validate_schema(f), [])
        for key, value in (("voice", "mystery"), ("frame_id", "x"), ("predicate_span", {"start": True,"end": 4,"text": "x"}), ("extra", 1)):
            bad = deepcopy(f)
            bad[key] = value
            self.assertTrue(validate_schema(bad), key)

    def test_28_source_change_detected(self):
        r = self.sample()
        r["inputs"] = ["Different source"]
        with self.assertRaises(ValueError):
            export_r1_observations(r)

    def test_29_disabled_frames_not_ready(self):
        r = PLMC2Engine(config=C2Config(use_relation_frames=False)).analyze("The bank granted aid to a river project.")
        self.assertFalse(r["r1_boundary"]["observation_ready"])

    def test_30_quoted_scope_quarantined(self):
        r = PLMC2Engine().analyze('The report says "the bank awarded grants for a river restoration".')
        self.assertEqual(r["semantic_audit"]["rule_checked_count"], 0)

    def test_38_duplicate_mentions_rejected(self):
        r = self.sample()
        r["mentions"].append(deepcopy(r["mentions"][0]))
        with self.assertRaises(ValueError):
            export_r1_observations(r)

    def test_39_missing_frame_node_rejected(self):
        r = self.sample()
        frame_id = r["relation_frames"][0]["frame_id"]
        r["claim_graph"]["nodes"] = [n for n in r["claim_graph"]["nodes"] if n["node_id"] != frame_id]
        r["claim_graph"]["edges"] = [e for e in r["claim_graph"]["edges"] if e["source"] != frame_id and e["target"] != frame_id]
        with self.assertRaises(ValueError):
            export_r1_observations(r)

    def test_40_unknown_source_relation_rejected(self):
        r = self.sample()
        r["relation_frames"][0]["source_relation_id"] = "R999999"
        with self.assertRaises(ValueError):
            export_r1_observations(r)


class TestEvaluationAndCalibration(unittest.TestCase):
    def test_31_development_gold_semantics(self):
        r = semantic_evaluate(PLMC2Engine(), load_v04_cases("development"))
        self.assertEqual(r["rule_checked"]["f1"], 1.0)
        self.assertEqual(r["constraint_failures"], [])

    def test_32_metamorphic_gold_roles(self):
        r = metamorphic_evaluate(PLMC2Engine())
        self.assertEqual(r["passed"], r["total"])

    def test_33_previous_datasets_preserved(self):
        for name in ("challenge_c2_v02.json", "challenge_c2_v03.json"):
            r = evaluate(PLMC2Engine(), load_cases(str(ROOT / "data" / name)), "v04", bootstrap_samples=0)
            self.assertEqual(r["metrics"]["top1_accuracy"], 1.0)

    def test_34_isotonic_monotonic_and_non_extreme(self):
        bins = fit_isotonic([{"signal": .1, "correct": True}, {"signal": .2,"correct": False}, {"signal": .9,"correct": True}])
        probs = [b["probability"] for b in bins]
        self.assertEqual(probs, sorted(probs))
        self.assertTrue(all(0 < p < 1 for p in probs))

    def test_35_calibrator_uses_only_its_split(self):
        with self.assertRaises(ValueError):
            fit_calibration(ROOT / "data" / "development_c2_v04.json")

    def test_36_confidence_preserves_target_and_diagnostics(self):
        r = PLMC2Engine().analyze(["A dog and another dog entered.", "It was photographed."])
        s = r["selections"]["entity"]
        self.assertEqual(s["reliability_signal"], .45)
        self.assertIn("unresolved_instance_reference", s["risk_flags"])
        self.assertIn("including_abstention", s["confidence_target"])

    def test_37_complete_runtime_manifest_when_present(self):
        if not (ROOT / "FREEZE_MANIFEST.json").exists():
            self.skipTest("runtime not frozen yet")
        self.assertTrue(verify_freeze()["valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
