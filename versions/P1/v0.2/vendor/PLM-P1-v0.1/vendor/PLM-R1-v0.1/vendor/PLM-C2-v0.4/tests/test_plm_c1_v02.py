import unittest

from plm_c0 import evaluate, load_cases
from plm_c1_v02 import C1Config, PLMC1Engine, run_suite


class TestPLMC1V02Engine(unittest.TestCase):
    def test_01_output_has_targets_relations_and_polarity_depth(self):
        result = PLMC1Engine().analyze("The bank is nowhere near a river.")
        self.assertEqual(result["version"], "PLM-C1 v0.2")
        self.assertTrue(result["targets"])
        self.assertTrue(result["relations"])
        self.assertIn("target_id", result["evidence"][0])
        self.assertIn("polarity_depth", result["evidence"][0])

    def test_02_double_negation_english(self):
        result = PLMC1Engine().analyze("It is not impossible that this is a dog.")
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")
        self.assertTrue(any(op["operation"] == "POLARITY_COMPOSE" for op in result["operations"]))

    def test_03_triple_negation_english(self):
        result = PLMC1Engine().analyze("It is not impossible that this is not a dog.")
        self.assertEqual(result["selections"]["entity"]["selected"], "UNRESOLVED")
        dog = next(item for item in result["evidence"] if item["concept"] == "DOG")
        self.assertEqual(dog["polarity_depth"], 3)

    def test_04_double_negation_japanese(self):
        result = PLMC1Engine().analyze("犬でないとは言えない")
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")

    def test_05_reported_denial(self):
        result = PLMC1Engine().analyze("The report denied that it was a dog.")
        self.assertEqual(result["selections"]["entity"]["selected"], "UNRESOLVED")

    def test_06_discourse_correction(self):
        result = PLMC1Engine().analyze("At first it looked like a dog; in fact it was a cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(op["operation"] == "STATE_TRANSITION" for op in result["operations"]))
        self.assertTrue(any(op["operation"] == "SUPERSEDE" for op in result["operations"]))

    def test_07_plural_morphology(self):
        result = PLMC1Engine().analyze("The bank stopped opening accounts.")
        self.assertEqual(result["selections"]["place"]["selected"], "FINANCIAL_BANK")
        self.assertTrue(any(item["pattern"] == "account" for item in result["evidence"]))

    def test_08_hypothetical_relation_is_not_applied(self):
        result = PLMC1Engine().analyze("If there were water, the bank would flood.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertTrue(result["relations"])
        self.assertFalse(result["relations"][0]["applied"])
        self.assertEqual(result["relations"][0]["reason"], "hypothetical relation")

    def test_09_negated_relation_is_not_applied(self):
        result = PLMC1Engine().analyze("The bank is nowhere near a river.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertEqual(result["relations"][0]["polarity"], -1)
        self.assertFalse(result["relations"][0]["applied"])

    def test_10_non_spatial_relation_is_not_applied(self):
        result = PLMC1Engine().analyze("The bank published a water policy.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertEqual(result["relations"][0]["reason"], "no supported relation between ambiguous term and trigger")

    def test_11_relation_ablation_reproduces_context_leak(self):
        engine = PLMC1Engine(config=C1Config(use_relation_context=False))
        result = engine.analyze("The bank published a water policy.")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")

    def test_12_target_tracking_isolates_instances(self):
        result = PLMC1Engine().analyze([
            "I opened an account at a bank.",
            "Afterward I walked along a river bank.",
        ])
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        place_targets = {
            item["target_id"] for item in result["evidence"]
            if item["concept"] in {"FINANCIAL_BANK", "RIVER_BANK"}
        }
        self.assertEqual(len(place_targets), 2)
        self.assertIn("place", result["diagnostics"]["forced_unresolved_domains"])


class TestPLMC1V02Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regression = [case for case in load_cases() if case["split"] == "test"]
        cls.known = load_cases("data/challenge_c1_v01.json")
        cls.unseen = load_cases("data/challenge_c1_v02.json")

    def test_13_frozen_regression_is_solved(self):
        report = evaluate(PLMC1Engine(), self.regression, "v0.2", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 1.0)

    def test_14_known_challenge_is_solved(self):
        report = evaluate(PLMC1Engine(), self.known, "v0.2", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 1.0)
        self.assertLess(report["metrics"]["expected_calibration_error"], 0.2)

    def test_15_unseen_challenge_is_frozen_and_nontrivial(self):
        self.assertEqual(len(self.unseen), 60)
        self.assertEqual(len({case["template_group"] for case in self.unseen}), 20)
        report = evaluate(PLMC1Engine(), self.unseen, "v0.2", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.65)

    def test_16_suite_reports_ablations_and_acceptance(self):
        suite = run_suite(bootstrap_samples=20)
        self.assertTrue(suite["acceptance_passed"])
        self.assertEqual(
            set(suite["ablations_on_known_challenge"]),
            {
                "full", "no_polarity_composition", "no_discourse_state",
                "no_morphology", "no_target_tracking", "no_relation_context",
                "no_residual",
            },
        )
        full = suite["ablations_on_known_challenge"]["full"]["metrics"]["top1_accuracy"]
        for name in ("no_polarity_composition", "no_discourse_state", "no_morphology", "no_target_tracking", "no_relation_context"):
            self.assertGreater(full, suite["ablations_on_known_challenge"][name]["metrics"]["top1_accuracy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
