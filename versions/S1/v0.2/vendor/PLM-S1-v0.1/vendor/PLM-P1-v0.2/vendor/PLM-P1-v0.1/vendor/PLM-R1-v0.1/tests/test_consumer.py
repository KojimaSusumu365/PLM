from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from plm_r1 import ObservationStore, analyze, export_observations
from plm_r1.contract import load_json, validate_envelope, canonical
from plm_r1.producer import verify_dependency, VENDOR
from plm_r1.store import markdown

ROOT = Path(__file__).resolve().parents[1]


class ConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = analyze("The bank granted aid.")
        cls.env = export_observations(cls.analysis)

    def setUp(self):
        self.store = ObservationStore()

    def tearDown(self):
        self.store.close()

    def test_dependency_frozen(self):
        self.assertEqual(verify_dependency()["verified_files"], 67)

    def test_roundtrip(self):
        self.store.ingest_analysis(self.analysis, source_id="source")
        doc = self.store.ledger()["documents"][0]
        self.assertEqual(doc["raw_inputs"], self.analysis["inputs"])
        self.assertEqual(doc["observations"][0]["original_frame"], self.env["observations"][0])
        self.assertEqual(doc["evidence"], self.env["evidence"])

    def test_idempotent_repeat(self):
        self.store.ingest(self.env, source_id="source")
        receipt = self.store.ingest(self.env, source_id="source")
        self.assertFalse(receipt["document_created"])
        self.assertFalse(receipt["source_link_created"])
        self.assertEqual(self.store.ledger()["observation_count"], len(self.env["observations"]))

    def test_same_content_two_sources(self):
        self.store.ingest(self.env, source_id="one")
        self.store.ingest(self.env, source_id="two")
        ledger = self.store.ledger()
        self.assertEqual(ledger["unique_content_count"], 1)
        self.assertEqual(ledger["source_revision_count"], 2)
        self.assertIsNone(ledger["independent_evidence_count"])

    def test_source_conflict_atomic(self):
        self.store.ingest(self.env, source_id="source")
        before = self.store.ledger()
        with self.assertRaises(ValueError):
            self.store.ingest_analysis(analyze("A dog entered."), source_id="source")
        self.assertEqual(before, self.store.ledger())

    def test_explicit_revision(self):
        self.store.ingest(self.env, source_id="source")
        self.store.ingest_analysis(analyze("A dog entered."), source_id="source", revision="2")
        self.assertEqual(self.store.ledger()["unique_content_count"], 2)

    def test_document_entity_namespace(self):
        self.store.ingest_analysis(self.analysis, source_id="one")
        self.store.ingest_analysis(analyze("The bank granted funds."), source_id="two")
        ids = [d["observations"][0]["qualified_subject_entity"] for d in self.store.ledger()["documents"]]
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(x.endswith(":ENT000001") for x in ids))

    def test_envelope_context_limitation(self):
        receipt = self.store.ingest(self.env, source_id="one")
        self.assertFalse(receipt["content_hash_verified"])
        self.assertFalse(receipt["graph_independently_validated"])
        self.assertIsNone(self.store.ledger()["documents"][0]["raw_inputs"])

    def test_context_enrichment(self):
        self.store.ingest(self.env, source_id="one")
        receipt = self.store.ingest_analysis(self.analysis, source_id="one")
        self.assertTrue(receipt["context_added"])
        self.assertTrue(receipt["content_hash_verified"])
        self.assertFalse(receipt["document_created"])

    def test_context_mismatch(self):
        with self.assertRaises(ValueError):
            self.store.ingest(self.env, source_id="one", analysis=analyze("A cat entered."))
        self.assertEqual(self.store.ledger()["unique_content_count"], 0)

    def test_context_conflict(self):
        self.store.ingest_analysis(self.analysis, source_id="one")
        other = deepcopy(self.analysis)
        other["selections"]["entity"]["selected"] = "TAMPERED"
        with self.assertRaises(ValueError):
            self.store.ingest_analysis(other, source_id="two")
        self.assertEqual(self.store.ledger()["source_revision_count"], 1)

    def test_immutable_payload(self):
        env = deepcopy(self.env)
        self.store.ingest(env, source_id="source")
        env["observations"][0]["subject"] = "edited"
        self.assertNotEqual(self.store.ledger()["documents"][0]["observations"][0]["original_frame"]["subject"], "edited")

    def test_semantic_claim_not_trusted(self):
        env = deepcopy(self.env)
        env["observations"][0]["subject"] = "incorrect_but_structurally_string"
        receipt = self.store.ingest(env, source_id="untrusted")
        self.assertEqual(receipt["semantic_validation"], "producer_claim_only")
        self.assertFalse(receipt["inference_enabled"])

    def test_inference_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.store.ingest(self.env, source_id="one", mode="infer")

    def test_empty_source_rejected(self):
        with self.assertRaises(ValueError):
            self.store.ingest(self.env, source_id=" ")

    def test_empty_document_visible(self):
        self.store.ingest_analysis(analyze([]), source_id="empty")
        doc = self.store.ledger()["documents"][0]
        self.assertEqual(doc["observations"], [])
        self.assertIn("no_relation_extracted_not_proof_of_absence", doc["notices"])

    def test_ambiguous_reference_visible(self):
        self.store.ingest_analysis(analyze(["A dog and another dog entered.", "It was photographed."]), source_id="ambiguous")
        doc = self.store.ledger()["documents"][0]
        self.assertTrue(any("reference_ambiguous" in n for n in doc["notices"]))
        self.assertEqual(len(doc["entities"]), 2)

    def test_plural_distinct_instances(self):
        self.store.ingest_analysis(analyze(["A dog and another dog entered.", "They were photographed."]), source_id="plural")
        doc = self.store.ledger()["documents"][0]
        ids = {o["qualified_object_entity"] for o in doc["observations"] if o["original_frame"]["relation_type"] == "COREFERENCE"}
        self.assertEqual(len(ids), 2)

    def test_revision_old_evidence(self):
        self.store.ingest_analysis(analyze("Originally marked dog: reclassified as cat."), source_id="revision")
        doc = self.store.ledger()["documents"][0]
        frame = doc["observations"][0]
        self.assertIsNotNone(frame["target_clause"])
        self.assertTrue(any(not e["active"] and e["superseded_by"] for e in frame["evidence"]))
        self.assertTrue(any(op["operation"] == "SUPERSEDE" for op in doc["operations"]))

    def test_negative_and_hypothetical_preserved(self):
        for text, flag in [("The bank did not grant aid.", "negative"), ("If the bank grants aid.", "hypothetical")]:
            self.store.ingest_analysis(analyze(text), source_id=flag)
        for doc in self.store.ledger()["documents"]:
            for obs in doc["observations"]:
                self.assertIn(doc["sources"][0]["source_id"], obs["review_flags"])
                self.assertFalse(obs["eligible_for_inference"])

    def test_quarantine_preserved(self):
        self.store.ingest_analysis(analyze('"The bank granted aid."'), source_id="quote")
        observations = self.store.ledger()["documents"][0]["observations"]
        self.assertTrue(observations)
        self.assertTrue(all(o["original_frame"]["semantic_status"] == "quarantined" for o in observations))

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "observations.sqlite3")
            with ObservationStore(path) as store:
                store.ingest_analysis(self.analysis, source_id="one")
                expected = store.ledger()
            with ObservationStore(path) as store:
                self.assertEqual(expected, store.ledger())

    def _review(self, **kwargs):
        self.store.ingest(self.env, source_id="one")
        args = dict(event_id="R1", document_id=self.env["document_id"], target_id=self.env["observations"][0]["observation_id"],
                    reviewer_id="test_only", decision="agrees_with_observation", error_types=[], note="Synthetic test review")
        args.update(kwargs)
        return self.store.review(**args)

    def test_review_does_not_promote(self):
        self._review()
        ledger = self.store.ledger()
        self.assertFalse(ledger["inference_enabled"])
        self.assertFalse(ledger["documents"][0]["reviews"][0]["eligible_for_inference"])
        self.assertEqual(ledger["documents"][0]["observations"][0]["original_frame"], self.env["observations"][0])

    def test_review_idempotent(self):
        self._review()
        self.assertFalse(self._review()["event_created"])

    def test_review_conflict(self):
        self._review()
        with self.assertRaises(ValueError):
            self._review(note="Changed in place")

    def test_review_history(self):
        self._review()
        self._review(event_id="R2", decision="disagrees", error_types=["subject_role"])
        self.assertEqual(len(self.store.ledger()["documents"][0]["reviews"]), 2)

    def test_review_missing_relation_document_target(self):
        self._review(target_id=self.env["document_id"], error_types=["missing_relation"])

    def test_review_target_rejected(self):
        with self.assertRaises(ValueError):
            self._review(target_id="another_document:F0001")

    def test_review_inference_decision_rejected(self):
        with self.assertRaises(ValueError):
            self._review(decision="approve_for_inference")

    def test_sql_append_only(self):
        self._review()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("DELETE FROM reviews")

    def test_markdown_escapes_untrusted_text(self):
        self._review(note="<script>alert(1)</script> | `code`")
        rendered = markdown(self.store.ledger())
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text('{"key": 1, "key": 2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json(path)

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            canonical({"bad": float("nan")})

    def test_all_integration_fixtures(self):
        for case in load_json(ROOT / "evaluation" / "integration_cases.json"):
            with self.subTest(case=case["case_id"]):
                self.store.ingest_analysis(analyze(case["inputs"]), source_id=case["case_id"])
        self.assertEqual(self.store.ledger()["unique_content_count"], 16)

    def test_known_failures_remain_visible(self):
        cases = load_json(ROOT / "evaluation" / "integration_cases.json")
        for case in cases:
            if "known_issue" in case:
                self.store.ingest_analysis(analyze(case["inputs"]), source_id=case["case_id"])
        docs = {d["sources"][0]["source_id"]: d for d in self.store.ledger()["documents"]}
        manager = docs["known_passive_agent_manager"]
        self.assertEqual(manager["producer_selections"]["place"]["selected"], "RIVER_BANK")
        self.assertEqual(manager["producer_selections"]["place"]["selection_confidence"], 0.9286)
        self.assertFalse(any(o["original_frame"]["semantic_status"] == "rule_checked" for o in manager["observations"]))
        self.assertEqual(docs["known_reassessed"]["producer_selections"]["entity"]["selected"], "ANIMAL")

    def test_all_c2_v04_dev_holdout_envelopes(self):
        count = 0
        for filename in ("development_c2_v04.json", "holdout_c2_v04.json"):
            for case in load_json(VENDOR / "data" / filename)["cases"]:
                with self.subTest(case=case["id"]):
                    self.store.ingest_analysis(analyze(case["inputs"]), source_id=filename + ":" + case["id"])
                    count += 1
        self.assertEqual(count, 55)


def mutation_test(mutate):
    def test(self):
        env = deepcopy(self.env)
        mutate(env)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.store.ingest(env, source_id="bad")
        self.assertEqual(self.store.ledger()["unique_content_count"], 0)
    return test


MUTATIONS = {
    "schema_version": lambda e: e.update(schema_version=True),
    "producer_version": lambda e: e.update(producer_version="PLM-C2 v9"),
    "document_hash": lambda e: e.update(document_id="not_a_hash"),
    "unknown_top_field": lambda e: e.update(facts=[]),
    "inference_enabled": lambda e: e["boundary"].update(inference_enabled=True),
    "inference_ready": lambda e: e["boundary"].update(inference_ready=True),
    "frame_inference": lambda e: e["observations"][0].update(eligible_for_inference=True),
    "positive_list": lambda e: e["boundary"].update(positive_rule_checked_frame_ids=[]),
    "observation_id": lambda e: e["observations"][0].update(observation_id="wrong:F0001"),
    "duplicate_frame": lambda e: e["observations"].append(deepcopy(e["observations"][0])),
    "duplicate_entity": lambda e: e["entities"].append(deepcopy(e["entities"][0])),
    "dangling_entity": lambda e: e["observations"][0].update(subject_entity_id="ENT999999"),
    "dangling_mention": lambda e: e["observations"][0].update(subject_mention_id="MN999999"),
    "dangling_evidence": lambda e: e["observations"][0].update(evidence_ids=["E9999"]),
    "dangling_clause": lambda e: e["observations"][0].update(clause_id="S999:C999"),
    "invalid_predicate_span": lambda e: e["observations"][0]["predicate_span"].update(start=999),
    "invalid_mention_span": lambda e: e["mentions"][0]["span"].update(text="not original"),
    "boolean_span_offset": lambda e: e["mentions"][0]["span"].update(start=True),
    "invalid_polarity": lambda e: e["observations"][0].update(polarity="maybe"),
    "missing_required": lambda e: e["observations"][0].pop("applied"),
    "dangling_supersession": lambda e: e["evidence"][0].update(active=False, superseded_by="E9999"),
    "self_supersession": lambda e: e["evidence"][0].update(active=False, superseded_by=e["evidence"][0]["evidence_id"]),
}
for name, mutation in MUTATIONS.items():
    setattr(ConsumerTests, "test_reject_" + name, mutation_test(mutation))


if __name__ == "__main__":
    unittest.main()
