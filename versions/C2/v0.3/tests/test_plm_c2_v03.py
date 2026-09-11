import unittest

from plm_c0 import evaluate, load_cases
from plm_c2 import C2Config, PLMC2Engine, run_suite
from plm_c2_v02 import PLMC2Engine as PLMC2V02Engine


class TestPLMC2V03Engine(unittest.TestCase):
    def test_01_version_relation_contract_and_graph_v2(self):
        result = PLMC2Engine().analyze("The bank granted aid to a river project.")
        self.assertEqual(result["version"], "PLM-C2 v0.3")
        self.assertEqual(result["claim_graph"]["schema_version"], 2)
        self.assertEqual(result["relation_contract"]["schema_version"], 1)
        self.assertTrue(result["relation_contract"]["ready_for_r1_experiment"])
        self.assertIn("RELATION_FRAME", {
            node["node_type"] for node in result["claim_graph"]["nodes"]
        })

    def test_02_relation_frames_have_required_fields(self):
        result = PLMC2Engine().analyze("The bank is near the river.")
        required = set(result["relation_contract"]["required_fields"])
        self.assertTrue(result["relation_frames"])
        for frame in result["relation_frames"]:
            self.assertTrue(required <= set(frame))
        self.assertTrue(result["claim_graph"]["invariants"]["relation_frame_required_fields"])

    def test_03_reclassified_is_a_corrective_role(self):
        result = PLMC2Engine().analyze("Originally marked dog: reclassified as cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(
            frame["relation_type"] == "REVISION" for frame in result["relation_frames"]
        ))

    def test_04_revision_role_family(self):
        cases = (
            "Originally marked dog: relabeled as cat.",
            "Originally marked dog: redesignated as cat.",
            "Originally marked dog. Changed the label to cat.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    PLMC2Engine().analyze(text)["selections"]["entity"]["selected"],
                    "CAT",
                )

    def test_05_revision_generalization_ablation(self):
        result = PLMC2Engine(
            config=C2Config(use_generalized_revision_roles=False)
        ).analyze("Originally marked dog: reclassified as cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")

    def test_06_extended_pair_references(self):
        cases = (
            ("The earlier one was selected.", "DOG"),
            ("The later one was selected.", "CAT"),
            ("The previous one was selected.", "CAT"),
        )
        for reference, expected in cases:
            with self.subTest(reference=reference):
                result = PLMC2Engine().analyze([
                    "A dog and a cat were listed.", reference,
                ])
                self.assertEqual(result["selections"]["entity"]["selected"], expected)

    def test_07_singular_pronoun_has_bounded_antecedent(self):
        result = PLMC2Engine().analyze(["A dog was examined.", "It was selected."])
        self.assertEqual(result["selections"]["entity"]["selected"], "DOG")
        self.assertEqual(result["reference_links"][0]["concept"], "DOG")

    def test_08_singular_pronoun_does_not_choose_between_two_mentions(self):
        result = PLMC2Engine().analyze([
            "A dog and a cat were examined.", "It was selected.",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")
        self.assertEqual(result["reference_links"], [])

    def test_09_plural_pronoun_resolves_as_a_set(self):
        result = PLMC2Engine().analyze([
            "A dog and a cat were examined.", "They were selected.",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")
        self.assertEqual({link["concept"] for link in result["reference_links"]}, {"DOG", "CAT"})

    def test_10_japanese_ordered_reference(self):
        result = PLMC2Engine().analyze(["犬と猫を記録した。", "後者を選んだ。"]) 
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")

    def test_11_extended_reference_ablation(self):
        result = PLMC2Engine(config=C2Config(use_extended_coreference=False)).analyze([
            "A dog and a cat were listed.", "The earlier one was selected.",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")

    def test_12_japanese_correction_scope(self):
        result = PLMC2Engine().analyze("犬、いや、猫。")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(
            operation["operation"] == "PROPAGATE_CORRECTION_SCOPE"
            for operation in result["operations"]
        ))

    def test_13_japanese_revision_role(self):
        result = PLMC2Engine().analyze("当初は犬：再分類すると猫。")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")

    def test_14_japanese_scope_ablation(self):
        result = PLMC2Engine(
            config=C2Config(use_japanese_correction_scope=False)
        ).analyze("犬、いや、猫。")
        self.assertEqual(result["selections"]["entity"]["selected"], "ANIMAL")

    def test_15_role_affordance_family(self):
        texts = (
            "The bank granted aid to a river project.",
            "The bank allocated resources to river research.",
            "The bank invested in a river restoration plan.",
            "The bank backed a river conservation program.",
        )
        for text in texts:
            with self.subTest(text=text):
                result = PLMC2Engine().analyze(text)
                self.assertEqual(result["selections"]["place"]["selected"], "FINANCIAL_BANK")

    def test_16_negated_role_affordance_is_not_applied(self):
        result = PLMC2Engine().analyze("The bank did not allocate aid to a river project.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        role_ops = [
            operation for operation in result["operations"]
            if operation["operation"] == "INFER_ROLE_AFFORDANCE"
        ]
        self.assertTrue(role_ops)
        self.assertFalse(role_ops[0]["applied"])

    def test_17_hypothetical_role_affordance_is_not_applied(self):
        result = PLMC2Engine().analyze("If the bank allocated aid to a river project, it would report it.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")

    def test_18_passive_role_does_not_license_subject_affordance(self):
        result = PLMC2Engine().analyze("The bank was supported by a river alliance.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertTrue(any(
            frame["voice"] == "passive" and not frame["applied"]
            for frame in result["relation_frames"]
        ))

    def test_19_role_affordance_ablation(self):
        result = PLMC2Engine(config=C2Config(use_role_affordances=False)).analyze(
            "The bank granted aid to a river project."
        )
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")

    def test_20_relation_frames_can_be_disabled(self):
        result = PLMC2Engine(config=C2Config(use_relation_frames=False)).analyze(
            "The bank granted aid to a river project."
        )
        self.assertEqual(result["relation_frames"], [])
        self.assertFalse(result["relation_contract"]["ready_for_r1_experiment"])

    def test_21_relation_aware_calibration_is_auditable(self):
        result = PLMC2Engine().analyze("The marten crossed the clearing.")
        selection = result["selections"]["entity"]
        self.assertIn("raw_selection_confidence", selection)
        self.assertIn("v02_selection_confidence", selection)
        self.assertGreaterEqual(selection["selection_confidence"], 0.78)
        self.assertLessEqual(selection["selection_confidence"], 0.94)

    def test_22_all_pre_v03_sets_are_solved(self):
        datasets = (
            [case for case in load_cases() if case["split"] == "test"],
            load_cases("data/challenge_c1_v01.json"),
            load_cases("data/challenge_c1_v02.json"),
            load_cases("data/challenge_c1_v03.json"),
            load_cases("data/challenge_c2_v01.json"),
            load_cases("data/challenge_c2_v02.json"),
        )
        for cases in datasets:
            report = evaluate(PLMC2Engine(), cases, "C2 v0.3", bootstrap_samples=0)
            self.assertGreaterEqual(report["metrics"]["top1_accuracy"], 0.98)

    def test_23_frozen_v02_results_are_unchanged(self):
        cases = load_cases("data/challenge_c2_v02.json")
        report = evaluate(PLMC2V02Engine(), cases, "C2 v0.2", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.95)
        self.assertEqual(report["metrics"]["expected_calibration_error"], 0.1497)

    def test_24_development_set_is_solved(self):
        cases = load_cases("data/development_c2_v03.json")
        report = evaluate(PLMC2Engine(), cases, "C2 v0.3", bootstrap_samples=0)
        self.assertEqual(len(cases), 30)
        self.assertEqual(report["metrics"]["top1_accuracy"], 1.0)


class TestPLMC2V03Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_cases("data/challenge_c2_v03.json")
        cls.suite = run_suite(bootstrap_samples=20)

    def test_25_unseen_challenge_shape(self):
        self.assertEqual(len(self.cases), 72)
        self.assertEqual(len({case["template_group"] for case in self.cases}), 24)

    def test_26_first_run_metrics_are_preserved(self):
        report = self.suite["unseen_c2_v03_challenge"]["c2_v03"]
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.9583)
        self.assertEqual(report["metrics"]["mrr"], 0.9688)
        self.assertEqual(report["metrics"]["expected_calibration_error"], 0.0998)
        failures = {
            row["template_group"] for row in report["cases"] if not row["top1_correct"]
        }
        self.assertEqual(failures, {"revision_reidentified"})

    def test_27_frozen_v02_is_beaten_on_unseen_challenge(self):
        section = self.suite["unseen_c2_v03_challenge"]
        self.assertEqual(section["c2_v02"]["metrics"]["top1_accuracy"], 0.4167)
        self.assertEqual(section["c2_v03"]["metrics"]["top1_accuracy"], 0.9583)

    def test_28_accuracy_ablations_have_effect(self):
        ablations = self.suite["ablations_on_c2_v03_development"]
        full = ablations["full"]["metrics"]["top1_accuracy"]
        self.assertEqual(full, 1.0)
        for name in (
            "no_generalized_revision_roles", "no_extended_coreference",
            "no_role_affordances", "no_japanese_correction_scope",
        ):
            self.assertLess(ablations[name]["metrics"]["top1_accuracy"], full)

    def test_29_relation_calibration_improves_ece(self):
        ablations = self.suite["ablations_on_c2_v03_development"]
        self.assertLess(
            ablations["full"]["metrics"]["expected_calibration_error"],
            ablations["no_relation_aware_calibration"]["metrics"][
                "expected_calibration_error"
            ],
        )

    def test_30_relation_contract_audit(self):
        audit = self.suite["graph_relation_audit"]
        self.assertEqual(audit["claim_graph_invariant_failures"], {})
        self.assertEqual(audit["relation_contract_failures"], 0)
        self.assertTrue(
            {"COREFERENCE", "REVISION", "FINANCIAL_AFFORDANCE", "SPATIAL_ASSOCIATION"}
            <= set(audit["relation_frame_types"])
        )
        self.assertIn("RELATION_FRAME", audit["claim_graph_node_types"])
        self.assertIn("FRAME_OF", audit["claim_graph_edge_relations"])

    def test_31_hashes_match_freeze_records(self):
        protocol = self.suite["protocol"]
        self.assertEqual(
            protocol["postimplementation_sha256"],
            "1147428babad6704dcd197557dcea81e62c69d53fd59e20594fbdc0515d84f26",
        )
        self.assertEqual(protocol["engine_sha256_at_freeze"], protocol["engine_sha256_current"])
        self.assertEqual(protocol["concepts_sha256_at_freeze"], protocol["concepts_sha256_current"])

    def test_32_acceptance_passes(self):
        self.assertEqual(len(self.suite["acceptance"]), 15)
        self.assertTrue(self.suite["acceptance_passed"])
        self.assertTrue(all(self.suite["acceptance"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
