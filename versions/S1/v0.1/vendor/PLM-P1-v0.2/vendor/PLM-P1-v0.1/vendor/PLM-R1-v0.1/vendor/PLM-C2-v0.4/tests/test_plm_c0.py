import copy
import unittest

from plm_c0 import (
    EngineConfig,
    PLMC0Engine,
    PositiveLexicalBaseline,
    compare,
    evaluate,
    load_cases,
    validate_cases,
)


class TestPLMC0Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = PLMC0Engine()

    def test_01_dog_bark(self):
        result = self.engine.analyze("犬が吠えている")
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")
        self.assertEqual(result["selections"]["action"]["selected"], "BARK")

    def test_02_paraphrase(self):
        result = self.engine.analyze([
            "犬が吠えている",
            "ワンちゃんがキャンキャン鳴いている",
            "イヌが声を出している",
            "dog is barking",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")

    def test_03_negation(self):
        result = self.engine.analyze("犬ではなく猫だった")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        dog = next(row for row in result["ranking"]["entity"] if row["concept"] == "DOG")
        self.assertGreater(dog["contradiction"], 0)

    def test_04_generic(self):
        self.assertEqual(
            self.engine.analyze("動物が吠えている")["selections"]["entity"]["selected"],
            "ANIMAL",
        )

    def test_05_financial_bank(self):
        self.assertEqual(
            self.engine.analyze("I opened a bank account for my money.")["selections"]["place"]["selected"],
            "FINANCIAL_BANK",
        )

    def test_06_river_bank(self):
        self.assertEqual(
            self.engine.analyze("We sat on the river bank near the water.")["selections"]["place"]["selected"],
            "RIVER_BANK",
        )

    def test_07_unknown(self):
        result = self.engine.analyze("量子もつれについて考える")
        self.assertTrue(
            all(result["selections"][domain]["selected"] == "UNRESOLVED" for domain in result["selections"])
        )

    def test_08_cat_sibling_contradiction(self):
        result = self.engine.analyze("猫が鳴いている")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        dog = next(row for row in result["ranking"]["entity"] if row["concept"] == "DOG")
        self.assertGreater(dog["contradiction"], 0)

    def test_09_narrowing(self):
        self.assertEqual(
            self.engine.analyze("この動物は犬です")["selections"]["entity"]["selected"],
            "DOG",
        )

    def test_10_vehicle(self):
        self.assertEqual(
            self.engine.analyze("自動車が走っている")["selections"]["entity"]["selected"],
            "VEHICLE",
        )


class TestV03Engine(unittest.TestCase):
    def test_11_version_and_diagnostics(self):
        result = PLMC0Engine().analyze("river bank")
        self.assertEqual(result["version"], "PLM-C0 v0.3")
        self.assertEqual(result["diagnostics"]["concepts_scored"], 11)
        self.assertGreater(result["diagnostics"]["patterns_checked"], 0)

    def test_12_ascii_boundaries_block_substrings(self):
        engine = PLMC0Engine()
        for text in ("hotdog", "scar", "humanity"):
            self.assertEqual(
                engine.analyze(text)["selections"]["entity"]["selected"],
                "UNRESOLVED",
            )

    def test_13_boundary_ablation_reproduces_false_positive(self):
        engine = PLMC0Engine(config=EngineConfig(strict_ascii_boundaries=False))
        self.assertEqual(engine.analyze("hotdog")["selections"]["entity"]["selected"], "DOG")

    def test_14_longest_match_suppresses_overlap(self):
        result = PLMC0Engine().analyze("river bank")
        patterns = [item["pattern"] for item in result["evidence"] if item["pattern"] != "[context]"]
        self.assertEqual(patterns, ["river bank"])
        self.assertEqual(result["diagnostics"]["overlap_matches_suppressed"], 2)

    def test_15_no_positive_evidence_has_abstention_confidence(self):
        selection = PLMC0Engine().analyze("未知語")["selections"]["entity"]
        self.assertEqual(selection["selected"], "UNRESOLVED")
        self.assertEqual(selection["selection_confidence"], 1.0)


class TestV03Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all_cases = load_cases()
        cls.test_cases = [case for case in cls.all_cases if case["split"] == "test"]
        cls.primary = evaluate(
            PLMC0Engine(), cls.test_cases, "PLM-C0 v0.3", bootstrap_samples=200
        )
        cls.baseline = evaluate(
            PositiveLexicalBaseline(), cls.test_cases, "baseline", bootstrap_samples=200
        )
        cls.comparison = compare(cls.primary, cls.baseline, bootstrap_samples=200)

    def test_16_dataset_size_and_splits(self):
        self.assertEqual(len(self.all_cases), 288)
        self.assertEqual(len(self.test_cases), 216)
        self.assertEqual(len({case["template_group"] for case in self.all_cases}), 72)

    def test_17_schema_validation(self):
        domains = {
            concept_id: concept["domain"]
            for concept_id, concept in PLMC0Engine().concepts.items()
        }
        summary = validate_cases(self.all_cases, domains)
        self.assertEqual(summary["splits"], {"dev": 72, "test": 216})

    def test_18_duplicate_ids_are_rejected(self):
        invalid = copy.deepcopy(self.all_cases[:2])
        invalid[1]["id"] = invalid[0]["id"]
        with self.assertRaises(ValueError):
            validate_cases(invalid)

    def test_19_primary_beats_baseline_top1(self):
        self.assertGreater(
            self.primary["metrics"]["top1_accuracy"],
            self.baseline["metrics"]["top1_accuracy"],
        )

    def test_20_extended_metrics_exist(self):
        for key in (
            "macro_f1",
            "expected_calibration_error",
            "brier_score",
            "coverage",
            "selective_accuracy",
        ):
            self.assertIn(key, self.primary["metrics"])
        self.assertEqual(len(self.primary["coverage_accuracy_curve"]), 6)

    def test_21_bootstrap_intervals_exist(self):
        interval = self.primary["confidence_intervals"]["top1_accuracy_95"]
        self.assertEqual(interval["clusters"], 72)
        self.assertLessEqual(interval["lower"], interval["upper"])
        delta = self.comparison["confidence_intervals"]["top1_delta_95"]
        self.assertLessEqual(delta["lower"], delta["upper"])

    def test_22_negation_ablation_is_worse_on_negation(self):
        no_negation = evaluate(
            PLMC0Engine(config=EngineConfig(use_negation=False)),
            self.test_cases,
            "no_negation",
            bootstrap_samples=0,
        )
        self.assertLess(
            no_negation["per_tag"]["negation"]["top1_accuracy"],
            self.primary["per_tag"]["negation"]["top1_accuracy"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
