from copy import deepcopy
import unittest
from plm_r1 import analyze
from plm_r1.evaluation import prepare, evaluate, relation_metrics, prediction_relations, validate_relations, slot_metrics, task_manifest


def span(start, end, source_index=0):
    return dict(source_index=source_index, start=start, end=end)


GOLD = {"relation_type": "FINANCIAL_AFFORDANCE", "anchor": span(9, 16),
        "subject": span(4, 8), "predicate": "grant", "object": span(17, 20), "target": None,
        "voice": "active", "polarity": "positive", "modality": "asserted"}


def corpus(text="The bank granted aid.", stratum="financial_active"):
    return [dict(source_id="synthetic-001", revision="1", source_group="synthetic-source",
                 stratum=stratum, provenance="Internal test, not an independent annotator", inputs=[text])]


def completed(text="The bank granted aid.", gold=None):
    batch = prepare(corpus(text), dataset_kind="synthetic")
    gold = [deepcopy(GOLD)] if gold is None else deepcopy(gold)
    item = batch["items"][0]
    item.update(status="adjudicated", annotations=[{"annotator_id": name, "relations": deepcopy(gold)} for name in ("mock-a", "mock-b")],
                adjudication={"adjudicator_id": "mock-c", "relations": deepcopy(gold), "rationale": "Synthetic scorer test, no independent judgment"})
    return batch


class EvaluationTests(unittest.TestCase):
    def test_blank_pending_not_success(self):
        report = evaluate(prepare([]))
        self.assertEqual(report["status"], "pending_inputs")
        self.assertIsNone(report["metrics"])
        self.assertIn("real_corpus_not_supplied", report["barriers"])

    def test_blind_task_has_no_prefilled_gold(self):
        batch = prepare(corpus(), dataset_kind="synthetic")
        self.assertEqual(batch["items"][0]["annotations"], [])
        self.assertIsNone(batch["items"][0]["adjudication"])
        self.assertNotIn("predictions", batch["items"][0])

    def test_pending_annotation_not_zero_gold(self):
        report = evaluate(prepare(corpus(), dataset_kind="synthetic"))
        self.assertIsNone(report["metrics"])

    def test_exact_handwritten_gold(self):
        report = evaluate(completed())
        self.assertEqual(report["status"], "scored_synthetic_only")
        self.assertEqual(report["metrics"], dict(tp=1, fp=0, fn=0, precision=1.0, recall=1.0, f1=1.0))
        self.assertFalse(report["inference_enabled"])

    def test_zero_gold_false_positive(self):
        report = evaluate(completed(gold=[]))
        self.assertEqual(report["metrics"]["fp"], 1)
        self.assertIsNone(report["metrics"]["recall"])

    def test_empty_both_is_undefined_f1(self):
        report = evaluate(completed("Clouds gather overhead.", gold=[]))
        self.assertIsNone(report["metrics"]["f1"])
        self.assertEqual(report["document_exact_count"], 1)

    def test_missing_gold_relation_is_false_negative(self):
        gold = dict(GOLD, anchor=span(9, 18), object=span(19, 22), predicate="disburse")
        report = evaluate(completed("The bank disbursed aid.", [gold]))
        self.assertEqual(report["metrics"]["fn"], 1)
        self.assertEqual(report["metrics"]["tp"], 0)

    def test_wrong_role_both_fp_and_fn(self):
        wrong = dict(GOLD, subject=GOLD["object"], object=GOLD["subject"])
        result = relation_metrics([wrong], [GOLD])
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))

    def test_duplicate_prediction_not_hidden(self):
        self.assertEqual(relation_metrics([GOLD, GOLD], [GOLD])["fp"], 1)

    def test_unmappable_counts_as_false_positive(self):
        self.assertEqual(relation_metrics([], [], unmappable_count=1)["fp"], 1)

    def test_negative_still_scored(self):
        relations, bad = prediction_relations(analyze("The bank did not grant aid."))
        self.assertFalse(bad)
        self.assertEqual(relations[0]["polarity"], "negative")

    def test_hypothetical_still_scored(self):
        relations, bad = prediction_relations(analyze("If the bank grants aid."))
        self.assertFalse(bad)
        self.assertEqual(relations[0]["modality"], "hypothetical")

    def test_quarantine_not_primary(self):
        result = analyze('"The bank granted aid."')
        self.assertEqual(prediction_relations(result), ([], []))
        raw, bad = prediction_relations(result, checked_only=False)
        self.assertGreater(len(raw) + len(bad), 0)

    def test_revision_source_offsets(self):
        inputs = "Originally marked dog: reclassified as cat."
        relations, bad = prediction_relations(analyze(inputs))
        self.assertFalse(bad)
        self.assertEqual(relations[0]["target"], span(0, 21))
        self.assertEqual(relations[0]["anchor"], span(23, 42))

    def test_coreference_source_identity(self):
        relations, bad = prediction_relations(analyze(["A dog and another dog entered.", "They were photographed."]))
        self.assertFalse(bad)
        self.assertEqual(len(relations), 2)
        self.assertNotEqual(relations[0]["object"], relations[1]["object"])
        self.assertEqual(relations[0]["anchor"]["source_index"], 1)

    def test_japanese_offsets(self):
        relations, bad = prediction_relations(analyze("犬、いや、猫。"))
        self.assertFalse(bad)
        self.assertTrue(relations)
        for relation in relations:
            validate_relations([relation], ["犬、いや、猫。"])

    def test_protocol_mismatch_rejected(self):
        batch = completed()
        batch["protocol_hash"] = "edited"
        with self.assertRaises(ValueError):
            evaluate(batch)

    def test_content_change_rejected(self):
        batch = completed()
        batch["items"][0]["inputs"] = ["The bank granted funds."]
        with self.assertRaises(ValueError):
            evaluate(batch)

    def test_duplicate_evaluation_document_rejected(self):
        rows = corpus()
        with self.assertRaises(ValueError):
            prepare(rows + rows, dataset_kind="synthetic")

    def test_prior_exposed_c2_text_rejected(self):
        with self.assertRaises(ValueError):
            prepare(corpus("A river plan was supported by the bank manager."))

    def test_fake_one_person_independence_rejected(self):
        batch = completed()
        batch["items"][0]["annotations"][1]["annotator_id"] = "mock-a"
        with self.assertRaises(ValueError):
            evaluate(batch)

    def test_annotator_cannot_adjudicate_self(self):
        batch = completed()
        batch["items"][0]["adjudication"]["adjudicator_id"] = "mock-a"
        with self.assertRaises(ValueError):
            evaluate(batch)

    def test_null_gold_rejected(self):
        batch = completed()
        batch["items"][0]["adjudication"]["relations"] = None
        with self.assertRaises(ValueError):
            evaluate(batch)

    def test_duplicate_gold_rejected(self):
        with self.assertRaises(ValueError):
            validate_relations([GOLD, GOLD], ["The bank granted aid."])

    def test_bad_offset_rejected(self):
        with self.assertRaises(ValueError):
            validate_relations([dict(GOLD, subject=span(-1, 8))], ["The bank granted aid."])

    def test_span_boolean_rejected(self):
        with self.assertRaises(ValueError):
            validate_relations([dict(GOLD, subject=span(True, 8))], ["The bank granted aid."])

    def test_missing_role_rejected(self):
        with self.assertRaises(ValueError):
            validate_relations([dict(GOLD, subject=None)], ["The bank granted aid."])

    def test_ambiguous_alignment_excluded_from_slot_denominator(self):
        values = slot_metrics([GOLD, GOLD], [GOLD])
        self.assertEqual(values["subject"]["aligned"], 0)

    def test_annotation_disagreement_visible(self):
        batch = completed()
        batch["items"][0]["annotations"][1]["relations"] = []
        self.assertEqual(evaluate(batch)["first_two_annotators_exact_document_agreement"], 0)

    def test_exclusion_not_silent(self):
        batch = prepare(corpus(), dataset_kind="synthetic")
        batch["items"][0].update(status="excluded", exclusion_reason="Unresolvable source ambiguity")
        report = evaluate(batch)
        self.assertEqual(len(report["exclusions"]), 1)
        self.assertIsNone(report["metrics"])

    def test_real_pilot_requires_process_and_sample(self):
        batch = prepare(corpus("Unpublished sample 527: clouds moved overhead."))
        report = evaluate(batch)
        self.assertIn("fewer_than_50_adjudicated_documents", report["barriers"])
        self.assertIn("missing_declaration:independent_of_implementation", report["barriers"])

    def test_task_manifest_verified(self):
        batch = completed()
        self.assertTrue(evaluate(batch, task_manifest(batch))["task_manifest_verified"])

    def test_task_manifest_rejects_sampling_change(self):
        batch = completed()
        manifest = task_manifest(batch)
        batch["items"][0]["stratum"] = "negative"
        with self.assertRaises(ValueError):
            evaluate(batch, manifest)

    def test_quoted_gold_supported_separately_from_c2(self):
        validate_relations([dict(GOLD, modality="quoted")], ["The bank granted aid."])


if __name__ == "__main__":
    unittest.main()
