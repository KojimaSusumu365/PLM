import unittest

from plm_c0 import evaluate, load_cases
from plm_c1 import C1Config, PLMC1Engine, run_suite


class TestPLMC1Engine(unittest.TestCase):
    def test_01_scoped_output_schema(self):
        result = PLMC1Engine().analyze("犬ではなく猫だった")
        self.assertEqual(result["version"], "PLM-C1 v0.1")
        self.assertTrue(result["clauses"])
        evidence = result["evidence"][0]
        for key in (
            "source_id", "clause_id", "scope", "assertion_status",
            "source_order", "active", "effective_weight",
        ):
            self.assertIn(key, evidence)

    def test_02_long_english_negation(self):
        result = PLMC1Engine().analyze("It is not really very clearly a dog.")
        self.assertEqual(result["selections"]["entity"]["selected"], "UNRESOLVED")
        self.assertTrue(any(op["operation"] == "NEGATE" for op in result["operations"]))

    def test_03_japanese_predicate_negation(self):
        result = PLMC1Engine().analyze("犬は吠えなかった")
        self.assertEqual(result["selections"]["action"]["selected"], "UNRESOLVED")

    def test_04_same_source_correction_supersedes(self):
        result = PLMC1Engine().analyze("犬だと思ったが、実際は猫だった")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        superseded = [item for item in result["evidence"] if not item["active"]]
        self.assertEqual([item["concept"] for item in superseded], ["DOG"])
        self.assertEqual(superseded[0]["effective_weight"], 0.0)
        self.assertTrue(any(op["operation"] == "SUPERSEDE" for op in result["operations"]))

    def test_05_cross_source_correction_supersedes(self):
        result = PLMC1Engine().analyze(["犬だ", "犬らしい", "訂正すると猫だった"])
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertEqual(result["diagnostics"]["superseded_evidence_items"], 2)

    def test_06_residual_ablation_retains_old_evidence(self):
        engine = PLMC1Engine(config=C1Config(use_residual=False))
        result = engine.analyze("犬だと思ったが、実際は猫だった")
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")
        self.assertTrue(any(op["operation"] == "SUPERSEDE_SKIPPED" for op in result["operations"]))

    def test_07_clause_local_context(self):
        result = PLMC1Engine().analyze("The bank was discussed while water spilled from a glass.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertEqual(result["diagnostics"]["clauses"], 2)

    def test_08_cross_input_context_is_not_leaked(self):
        result = PLMC1Engine().analyze(["The bank was mentioned.", "Separately, water spilled."])
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")

    def test_09_negated_river_context_is_not_boosted(self):
        result = PLMC1Engine().analyze("The bank has no water nearby.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")

    def test_10_financial_affordance_survives_predicate_negation(self):
        result = PLMC1Engine().analyze("The bank does not offer loans.")
        self.assertEqual(result["selections"]["place"]["selected"], "FINANCIAL_BANK")

    def test_11_isolated_instances_force_abstention(self):
        result = PLMC1Engine().analyze(["I visited a bank.", "Later I crossed a river."])
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertIn("place", result["diagnostics"]["forced_unresolved_domains"])
        self.assertTrue(any(op["operation"] == "ISOLATE_CONFLICT" for op in result["operations"]))

    def test_12_scope_ablation_reproduces_context_leak(self):
        engine = PLMC1Engine(config=C1Config(use_scope=False))
        result = engine.analyze("The bank was discussed while water spilled from a glass.")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")

    def test_13_ascii_to_japanese_boundary(self):
        result = PLMC1Engine().analyze("bankのそばを川が流れる")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")


class TestPLMC1Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regression = [case for case in load_cases() if case["split"] == "test"]
        cls.challenge = load_cases("data/challenge_c1_v01.json")

    def test_14_frozen_regression_is_solved(self):
        report = evaluate(
            PLMC1Engine(), self.regression, "C1", bootstrap_samples=0
        )
        self.assertEqual(report["metrics"]["top1_accuracy"], 1.0)
        self.assertEqual(report["per_tag"]["stress"]["top1_accuracy"], 1.0)

    def test_15_challenge_is_frozen_and_nontrivial(self):
        self.assertEqual(len(self.challenge), 60)
        self.assertEqual(len({case["template_group"] for case in self.challenge}), 20)
        report = evaluate(
            PLMC1Engine(), self.challenge, "C1 challenge", bootstrap_samples=0
        )
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.2)

    def test_16_suite_reports_required_ablations(self):
        suite = run_suite(bootstrap_samples=20)
        self.assertEqual(
            set(suite["ablations"]),
            {"full", "no_scope", "no_correction", "no_residual", "no_negation"},
        )
        self.assertGreater(
            suite["ablations"]["full"]["metrics"]["top1_accuracy"],
            suite["ablations"]["no_scope"]["metrics"]["top1_accuracy"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
