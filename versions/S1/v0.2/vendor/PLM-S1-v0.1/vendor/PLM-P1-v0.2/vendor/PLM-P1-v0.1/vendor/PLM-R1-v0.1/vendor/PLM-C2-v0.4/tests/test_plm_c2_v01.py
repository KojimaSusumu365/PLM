import unittest

from plm_c0 import evaluate, load_cases
from plm_c1 import PLMC1Engine as PLMC1V03Engine
from plm_c2_v01 import C2Config, PLMC2Engine, run_suite


class TestPLMC2V01Engine(unittest.TestCase):
    def test_01_version_and_typed_graph_schema(self):
        result = PLMC2Engine().analyze("A dog barked.")
        self.assertEqual(result["version"], "PLM-C2 v0.1")
        graph = result["claim_graph"]
        self.assertEqual(graph["schema_version"], 1)
        self.assertTrue(graph["invariants"]["unique_node_ids"])
        self.assertTrue(graph["invariants"]["edges_resolve"])
        node_types = {node["node_type"] for node in graph["nodes"]}
        self.assertTrue({"SOURCE", "CLAUSE", "EVENT", "ENTITY", "CONCEPT", "EVIDENCE"} <= node_types)

    def test_02_graph_edges_resolve_to_existing_nodes(self):
        graph = PLMC2Engine().analyze("The bank is near the river.")["claim_graph"]
        ids = {node["node_id"] for node in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["source"], ids)
            self.assertIn(edge["target"], ids)
        self.assertIn("RELATION", {node["node_type"] for node in graph["nodes"]})

    def test_03_period_boundary_preserves_decimal_and_splits_events(self):
        result = PLMC2Engine().analyze(
            "A dog weighs 3.5 kg. In a separate case, a cat slept."
        )
        self.assertEqual(len(result["clauses"]), 2)
        self.assertIn("3.5", result["clauses"][0]["text"])
        self.assertEqual(result["selections"]["entity"]["selected"], "UNRESOLVED")

    def test_04_temporal_relation_shifts_target(self):
        result = PLMC2Engine().analyze([
            "A dog was examined.",
            "Subsequently, a cat was examined.",
        ])
        self.assertEqual(result["selections"]["entity"]["selected"], "UNRESOLVED")
        self.assertTrue(any(op["operation"] == "TARGET_SHIFT" for op in result["operations"]))
        self.assertEqual(result["event_links"][0]["relation"], "NEXT_DISTINCT_TARGET")

    def test_05_revision_relation_supersedes_original(self):
        result = PLMC2Engine().analyze("Originally labeled a dog. Revised finding: cat.")
        self.assertEqual(result["selections"]["entity"]["selected"], "CAT")
        self.assertTrue(any(op["operation"] == "SUPERSEDE" for op in result["operations"]))

    def test_06_irregular_lemma_bitten(self):
        result = PLMC2Engine().analyze("The animal had been bitten.")
        self.assertEqual(result["selections"]["action"]["selected"], "BITE")
        self.assertEqual(result["normalizations"][0]["method"], "irregular_lemma")
        self.assertTrue(any(op["operation"] == "NORMALIZE_IRREGULAR" for op in result["operations"]))

    def test_07_irregular_boundary_does_not_match_bitter(self):
        result = PLMC2Engine().analyze("A bitter taste remained.")
        self.assertEqual(result["selections"]["action"]["selected"], "UNRESOLVED")
        self.assertFalse(any(item["concept"] == "BITE" for item in result["evidence"]))

    def test_08_closed_compound_riverbank(self):
        result = PLMC2Engine().analyze("They rested on the riverbank.")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")
        self.assertEqual(result["normalizations"][0]["method"], "closed_compound")

    def test_09_non_spatial_river_evidence_is_relation_gated(self):
        result = PLMC2Engine().analyze("The bank reviewed river statistics.")
        self.assertEqual(result["selections"]["place"]["selected"], "UNRESOLVED")
        self.assertEqual(result["diagnostics"]["relation_gated_evidence"], 1)
        self.assertTrue(any(op["operation"] == "RELATION_GATE" for op in result["operations"]))

    def test_10_typed_relation_gate_ablation_restores_old_error(self):
        engine = PLMC2Engine(config=C2Config(use_typed_relation_gate=False))
        result = engine.analyze("The bank reviewed river statistics.")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")

    def test_11_spatial_relation_remains_grounded(self):
        result = PLMC2Engine().analyze("The bank is near the river.")
        self.assertEqual(result["selections"]["place"]["selected"], "RIVER_BANK")
        self.assertTrue(result["relations"][0]["applied"])
        self.assertTrue(any(edge["relation"] == "GROUNDS" for edge in result["claim_graph"]["edges"]))

    def test_12_claim_graph_can_be_disabled(self):
        result = PLMC2Engine(config=C2Config(use_typed_claim_graph=False)).analyze("A dog barked.")
        self.assertEqual(result["claim_graph"]["nodes"], [])
        self.assertTrue(result["claim_graph"]["invariants"]["disabled"])


class TestPLMC2V01Evaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.regression = [case for case in load_cases() if case["split"] == "test"]
        cls.c1_v01 = load_cases("data/challenge_c1_v01.json")
        cls.c1_v02 = load_cases("data/challenge_c1_v02.json")
        cls.c1_v03 = load_cases("data/challenge_c1_v03.json")
        cls.c2 = load_cases("data/challenge_c2_v01.json")

    def test_13_all_known_sets_are_solved(self):
        for cases in (self.regression, self.c1_v01, self.c1_v02, self.c1_v03):
            report = evaluate(PLMC2Engine(), cases, "C2", bootstrap_samples=0)
            self.assertEqual(report["metrics"]["top1_accuracy"], 1.0)

    def test_14_unseen_challenge_is_frozen_and_nontrivial(self):
        self.assertEqual(len(self.c2), 60)
        self.assertEqual(len({case["template_group"] for case in self.c2}), 20)
        report = evaluate(PLMC2Engine(), self.c2, "C2", bootstrap_samples=0)
        self.assertEqual(report["metrics"]["top1_accuracy"], 0.8)
        self.assertEqual(report["metrics"]["expected_calibration_error"], 0.2582)

    def test_15_unseen_failures_are_preserved(self):
        report = evaluate(PLMC2Engine(), self.c2, "C2", bootstrap_samples=0)
        failures = {row["template_group"] for row in report["cases"] if not row["top1_correct"]}
        self.assertEqual(
            failures,
            {"coreference_latter", "correction_rather", "relation_sponsored_cleanup", "revision_colon"},
        )

    def test_16_c2_beats_frozen_c1_v03_on_unseen_set(self):
        c2 = evaluate(PLMC2Engine(), self.c2, "C2", bootstrap_samples=0)
        c1 = evaluate(PLMC1V03Engine(), self.c2, "C1", bootstrap_samples=0)
        self.assertEqual(c1["metrics"]["top1_accuracy"], 0.35)
        self.assertGreater(c2["metrics"]["top1_accuracy"], c1["metrics"]["top1_accuracy"])

    def test_17_suite_reports_all_ablations(self):
        suite = run_suite(bootstrap_samples=20)
        self.assertEqual(
            set(suite["ablations_on_v03_challenge"]),
            {
                "full", "no_sentence_boundaries", "no_temporal_relations",
                "no_revision_relations", "no_irregular_lemmas", "no_closed_compounds",
                "no_typed_relation_gate", "no_typed_claim_graph",
            },
        )
        full = suite["ablations_on_v03_challenge"]["full"]["metrics"]["top1_accuracy"]
        for name in (
            "no_sentence_boundaries", "no_temporal_relations", "no_revision_relations",
            "no_irregular_lemmas", "no_closed_compounds", "no_typed_relation_gate",
        ):
            self.assertGreater(full, suite["ablations_on_v03_challenge"][name]["metrics"]["top1_accuracy"])

    def test_18_graph_audit_has_no_invariant_failures(self):
        suite = run_suite(bootstrap_samples=0)
        audit = suite["graph_operation_audit"]
        self.assertEqual(audit["claim_graph_invariant_failures"], {})
        self.assertIn("EVENT", audit["claim_graph_node_types"])
        self.assertIn("GROUNDS", audit["claim_graph_edge_relations"])

    def test_19_challenge_hash_is_recorded(self):
        suite = run_suite(bootstrap_samples=0)
        self.assertEqual(
            suite["protocol"]["postimplementation_sha256"],
            "fd87b7663e9912b4898c8023f65c54955d826fdf8782631adb12d490ec6c1c85",
        )

    def test_20_acceptance_passes(self):
        suite = run_suite(bootstrap_samples=20)
        self.assertTrue(suite["acceptance_passed"])
        self.assertTrue(all(suite["acceptance"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
