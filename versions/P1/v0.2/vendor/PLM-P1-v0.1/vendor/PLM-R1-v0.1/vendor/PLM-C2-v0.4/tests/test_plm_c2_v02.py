import unittest

from plm_c0 import evaluate, load_cases
from plm_c2_v02 import C2Config, PLMC2Engine, run_suite
from plm_c2_v01 import PLMC2Engine as PLMC2V01Engine


class TestPLMC2V02Engine(unittest.TestCase):
    def test_01_version_and_reference_graph_schema(self):
        result = PLMC2Engine().analyze([
            "A dog and a cat were observed.",
            "The latter was selected.",
        ])
        self.assertEqual(result["version"], "PLM-C2 v0.2")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertEqual(result["reference_links"][0]["concept"], "CAT")
        self.assertTrue(result["claim_graph"]["invariants"]["edges_resolve"])
        self.assertIn("REFERENCE", {
            node["node_type"] for node in result["claim_graph"]["nodes"]
        })
        relations = {edge["relation"] for edge in result["claim_graph"]["edges"]}
        self.assertTrue({"RESOLVES_TO", "REFERS_BACK_TO"} <= relations)

    def test_02_former_first_and_second_resolve_in_order(self):
        pairs = (
            ("The former was selected.", "DOG"),
            ("The first was selected.", "DOG"),
            ("The second was selected.", "CAT"),
        )
        for reference, expected in pairs:
            with self.subTest(reference=reference):
                result = PLMC2Engine().analyze([
                    "A dog and a cat were observed.", reference,
                ])
                self.assertEqual(result["selections"]["entity"]["selected"], expected)

    def test_03_coreference_ablation_preserves_v01_behavior(self):
        result = PLMC2Engine(config=C2Config(use_ordered_coreference=False)).analyze([
            "A dog and a cat were observed.", "The latter was selected.",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")

    def test_04_rather_correction(self):
        result = PLMC2Engine().analyze("It was not a dog, rather a cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertIn("MARK_CONTRASTIVE_CORRECTION", {
            operation["operation"] for operation in result["operations"]
        })

    def test_05_instead_correction_supersedes_prior_label(self):
        result = PLMC2Engine().analyze("The label was dog, instead cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(
            operation["operation"] == "SUPERSEDE" for operation in result["operations"]
        ))

    def test_06_comparative_rather_than_is_not_a_correction_boundary(self):
        result = PLMC2Engine().analyze("A dog rather than an unknown item was selected.")
        self.assertEqual(len(result["clauses"]), 1)
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")
        self.assertFalse(any(
            operation["operation"] == "MARK_CONTRASTIVE_CORRECTION"
            for operation in result["operations"]
        ))

    def test_07_structural_revision_colon(self):
        result = PLMC2Engine().analyze(
            "Originally labeled a dog: revised finding labels it a cat."
        )
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertIn("SPLIT_REVISION_BOUNDARY", {
            operation["operation"] for operation in result["operations"]
        })

    def test_08_revision_boundary_ablation_preserves_v01_behavior(self):
        result = PLMC2Engine(
            config=C2Config(use_structural_revision_boundaries=False)
        ).analyze("Originally labeled a dog: revised finding labels it a cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")

    def test_09_agentive_affordance_selects_financial_bank(self):
        result = PLMC2Engine().analyze("The bank sponsored a river cleanup project.")
        self.assertEqual(result["selections"]["place"]["selected"], "FINANCIAL_BANK")
        inferred = [
            operation for operation in result["operations"]
            if operation["operation"] == "INFER_AGENTIVE_AFFORDANCE"
        ]
        self.assertTrue(inferred)
        self.assertTrue(inferred[0]["applied"])

    def test_10_negated_agentive_affordance_is_not_applied(self):
        result = PLMC2Engine().analyze("The bank did not sponsor a river cleanup project.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        inferred = [
            operation for operation in result["operations"]
            if operation["operation"] == "INFER_AGENTIVE_AFFORDANCE"
        ]
        self.assertTrue(inferred)
        self.assertFalse(inferred[0]["applied"])

    def test_11_passive_sponsorship_is_not_a_spatial_bank_relation(self):
        result = PLMC2Engine().analyze("The bank was sponsored by a river group.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")

    def test_12_agentive_ablation_preserves_v01_behavior(self):
        result = PLMC2Engine(config=C2Config(use_agentive_affordances=False)).analyze(
            "The bank sponsored a river cleanup project."
        )
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")

    def test_13_conservative_calibration_is_bounded_and_auditable(self):
        result = PLMC2Engine().analyze("The otter floated quietly.")
        selection = result["selections"]["entity"]
        self.assertEqual(selection["selected"], "UNRESOLVED")
        self.assertGreaterEqual(selection["selection_confidence"], 0.70)
        self.assertLessEqual(selection["selection_confidence"], 0.93)
        self.assertIn("raw_selection_confidence", selection)

    def test_14_all_pre_v02_sets_are_solved(self):
        datasets = (
            [case for case in load_cases() if case["split"] == "test"],
            load_cases("data/challenge_c1_v01.json"),
            load_cases("data/challenge_c1_v02.json"),
            load_cases("data/challenge_c1_v03.json"),
            load_cases("data/challenge_c2_v01.json"),
        )
        for cases in datasets:
            report = evaluate(PLMC2Engine(), cases, "C2 v0.2", bootstrap_samples=0)
            self.assertEqual(report["metrics"]["top1_accuracy"], 1.0)

    def test_15_frozen_v01_results_are_unchanged(self):
        cases = load_cases("data/challenge_c2_v01.json")
        report = evaluate(PLMC2V01Engine(), cases, "C2 v0.1", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.8)
        self.assertEqual(report["metrics"]["expected_calibration_error"], 0.2582)


class TestPLMC2V02Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases("data/challenge_c2_v02.json")
        cls.suite = run_suite(bootstrap_samples=20)

    def test_16_unseen_challenge_shape(self):
        self.assertEqual(len(self.cases), 60)
        self.assertEqual(len({case["template_group"] for case in self.cases}), 20)

    def test_17_first_run_metrics_are_preserved(self):
        metrics = self.suite["unseen_c2_v02_challenge"]["c2_v02"]["metrics"]
        self.assertEqual(metrics["top1_accuracy"], 0.95)
        self.assertEqual(metrics["mrr"], 0.9625)
        self.assertEqual(metrics["expected_calibration_error"], 0.1497)
        failures = {
            row["template_group"]
            for row in self.suite["unseen_c2_v02_challenge"]["c2_v02"]["cases"]
            if not row["top1_correct"]
        }
        self.assertEqual(failures, {"revision_reclassified_colon"})

    def test_18_frozen_v01_is_beaten_on_unseen_challenge(self):
        section = self.suite["unseen_c2_v02_challenge"]
        self.assertEqual(section["c2_v01"]["metrics"]["top1_accuracy"], 0.25)
        self.assertEqual(section["c2_v02"]["metrics"]["top1_accuracy"], 0.95)

    def test_19_accuracy_ablations_have_effect(self):
        ablations = self.suite["ablations_on_c2_v01_challenge"]
        self.assertEqual(ablations["full"]["metrics"]["top1_accuracy"], 1.0)
        for name in (
            "no_structural_revision_boundaries", "no_contrastive_corrections",
            "no_ordered_coreference", "no_agentive_affordances",
        ):
            self.assertEqual(ablations[name]["metrics"]["top1_accuracy"], 0.95)

    def test_20_calibration_ablation_is_worse(self):
        ablations = self.suite["ablations_on_c2_v01_challenge"]
        full = ablations["full"]["metrics"]["expected_calibration_error"]
        without = ablations["no_conservative_calibration"]["metrics"][
            "expected_calibration_error"
        ]
        self.assertLess(full, without)

    def test_21_hashes_and_graph_audit(self):
        protocol = self.suite["protocol"]
        self.assertEqual(
            protocol["postimplementation_sha256"],
            "0a35d31af985633987ae465e7c91c340be20cabcbe820431981b5de208804717",
        )
        self.assertEqual(protocol["engine_sha256_at_freeze"], protocol["engine_sha256_current"])
        audit = self.suite["graph_operation_audit"]
        self.assertEqual(audit["claim_graph_invariant_failures"], {})
        self.assertIn("REFERENCE", audit["claim_graph_node_types"])
        self.assertIn("RESOLVES_TO", audit["claim_graph_edge_relations"])
        self.assertIn("INFER_AGENTIVE_AFFORDANCE", audit["operation_counts"])

    def test_22_acceptance_passes(self):
        self.assertTrue(self.suite["acceptance_passed"])
        self.assertTrue(all(self.suite["acceptance"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
