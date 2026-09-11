import unittest

from plm_c0 import evaluate, load_cases
from plm_c1 import C1Config, PLMC1Engine, run_suite


class TestPLMC1V03Engine(unittest.TestCase):
    def test_01_output_schema_and_version(self):
        result = PLMC1Engine().analyze("Several puppies were asleep.")
        self.assertEqual(result["version"], "PLM-C1 v0.3")
        self.assertIn("normalizations", result)
        self.assertEqual(result["normalizations"][0]["method"], "inflection")
        self.assertIn("open_set_domains", result["diagnostics"])

    def test_02_irregular_plural_normalization(self):
        result = PLMC1Engine().analyze("Several puppies were asleep.")
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")
        self.assertEqual(result["normalizations"][0]["surface"], "puppies")
        self.assertEqual(result["normalizations"][0]["lemma"], "puppy")

    def test_03_past_tense_normalization(self):
        result = PLMC1Engine().analyze("The animal barked loudly.")
        self.assertEqual(result["selections"]["action"]["selected"], "BARK")
        self.assertTrue(any(op["operation"] == "NORMALIZE_MORPHOLOGY" for op in result["operations"]))

    def test_04_progressive_normalization(self):
        result = PLMC1Engine().analyze("The animal was vocalizing.")
        self.assertEqual(result["selections"]["action"]["selected"], "VOCALIZE")

    def test_05_noun_morphology_does_not_match_cared_as_car(self):
        result = PLMC1Engine().analyze("The person cared deeply.")
        self.assertEqual(result["selections"]["entity"]["selected"], "HUMAN")
        self.assertFalse(any(item["concept"] == "VEHICLE" for item in result["evidence"]))

    def test_06_revision_roles_supersede_preliminary_finding(self):
        result = PLMC1Engine().analyze("Preliminary finding: dog; verified finding: cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(op["operation"] == "SUPERSEDE" for op in result["operations"]))

    def test_07_explicit_retraction_removes_residual(self):
        result = PLMC1Engine().analyze(
            "The dog classification was ruled out; the cat classification remained."
        )
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(op["operation"] == "RETRACT" for op in result["operations"]))
        dog = next(item for item in result["evidence"] if item["concept"] == "DOG")
        self.assertFalse(dog["active"])

    def test_08_japanese_retraction(self):
        result = PLMC1Engine().analyze("犬という判定を撤回、猫を確認済み")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(op["operation"] == "RETRACT" for op in result["operations"]))

    def test_09_event_identity_creates_distinct_targets(self):
        result = PLMC1Engine().analyze([
            "A dog was logged.",
            "Another instance contains a cat.",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "UNRESOLVED")
        self.assertEqual(len(result["targets"]), 2)
        self.assertTrue(any(op["operation"] == "TARGET_SHIFT" for op in result["operations"]))

    def test_10_approved_compound_is_segmented(self):
        result = PLMC1Engine().analyze("The bank runs along the riverfront.")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")
        self.assertEqual(result["normalizations"][0]["method"], "approved_compound")

    def test_11_open_set_confidence_is_conservative(self):
        result = PLMC1Engine().analyze("The quokka rested quietly.")
        selection = result["selections"]["entity"]
        self.assertEqual(selection["selected"], "UNRESOLVED")
        self.assertEqual(selection["selection_confidence"], 0.35)
        self.assertTrue(selection["open_set"])

    def test_12_open_set_ablation_retains_legacy_confidence(self):
        engine = PLMC1Engine(config=C1Config(use_open_set_confidence=False))
        selection = engine.analyze("The quokka rested quietly.")["selections"]["entity"]
        self.assertEqual(selection["selection_confidence"], 1.0)
        self.assertNotIn("open_set", selection)


class TestPLMC1V03Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regression = [case for case in load_cases() if case["split"] == "test"]
        cls.challenge_v01 = load_cases("data/challenge_c1_v01.json")
        cls.challenge_v02 = load_cases("data/challenge_c1_v02.json")
        cls.challenge_v03 = load_cases("data/challenge_c1_v03.json")

    def test_13_all_known_sets_meet_targets(self):
        for cases in (self.regression, self.challenge_v01, self.challenge_v02):
            report = evaluate(PLMC1Engine(), cases, "v0.3", bootstrap_samples=0)
            self.assertGreaterEqual(report["metrics"]["top1_accuracy"], 0.98)

    def test_14_unseen_challenge_is_frozen_and_nontrivial(self):
        self.assertEqual(len(self.challenge_v03), 60)
        self.assertEqual(len({case["template_group"] for case in self.challenge_v03}), 20)
        report = evaluate(PLMC1Engine(), self.challenge_v03, "v0.3", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.7)
        self.assertEqual(report["metrics"]["expected_calibration_error"], 0.1288)

    def test_15_unseen_failures_are_preserved(self):
        report = evaluate(PLMC1Engine(), self.challenge_v03, "v0.3", bootstrap_samples=0)
        failures = {row["template_group"] for row in report["cases"] if not row["top1_correct"]}
        self.assertEqual(
            failures,
            {
                "compound_riverbank_closed", "morph_bitten", "relation_river_statistics",
                "revision_originally_revised", "target_separate_case_inline",
                "target_subsequently",
            },
        )

    def test_16_suite_reports_feature_ablations(self):
        suite = run_suite(bootstrap_samples=20)
        self.assertTrue(suite["acceptance_passed"])
        expected = {
            "full", "no_lemma_normalization", "no_transition_roles", "no_event_identity",
            "no_compound_analysis", "no_open_set_confidence", "no_residual",
        }
        self.assertEqual(set(suite["ablations_on_v02_challenge"]), expected)
        full = suite["ablations_on_v02_challenge"]["full"]["metrics"]["top1_accuracy"]
        for name in (
            "no_lemma_normalization", "no_transition_roles", "no_event_identity",
            "no_compound_analysis", "no_residual",
        ):
            self.assertGreater(
                full,
                suite["ablations_on_v02_challenge"][name]["metrics"]["top1_accuracy"],
            )

    def test_17_open_set_confidence_improves_unseen_calibration(self):
        suite = run_suite(bootstrap_samples=0)
        ablation = suite["open_set_calibration_ablation_on_unseen_v03"]
        self.assertLess(
            ablation["full"]["metrics"]["expected_calibration_error"],
            ablation["no_open_set_confidence"]["metrics"]["expected_calibration_error"],
        )

    def test_18_challenge_hash_is_recorded(self):
        suite = run_suite(bootstrap_samples=0)
        self.assertEqual(
            suite["protocol"]["postimplementation_sha256"],
            "90a8f9d28b5e2abd86a66b9c60d309992c6c30c123586afcdf51751453e544a8",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
