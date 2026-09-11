import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v02.compat import Book, generator, canonical
from plm_l1_v02.features import Space, descriptor, abstract, tokenize, validate_lexicon
from plm_l1_v02.training import fit, observations
from plm_l1_v02.runtime import PairReader
from plm_l1_v02.memory import Association
from plm_l1_v02.bridge import translate, generate
from evaluation_support import load_data, transform, marker_map, rename_text, LookupReader, interpret, INVALID


class PairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, cls.dev, cls.lex = load_data("train"), load_data("development"), load_data("lexicon")
        cls.reader, cls.gen = fit(cls.train, cls.lex), generator()
        cls.text = "太郎が花子を助けた。"
        cls.packet = cls.reader.read(cls.text)["packet"]

    def test_development_read_and_generate(self):
        for row in self.dev:
            with self.subTest(text=row["text"]):
                read = self.reader.read(row["text"])
                self.assertEqual(read["status"], "read")
                self.assertEqual(self.reader.recover(read["packet"])["slots"], row["meaning"])
                for goal in ("subject_first", "object_first"):
                    out = generate(self.reader, read["packet"], self.gen, goal)
                    self.assertEqual(out["status"], "generated")
                    self.assertEqual(interpret(out["text"]), row["meaning"])

    def test_teacher_and_old_reader_not_called(self):
        import plm_l1.teacher as teacher
        with patch.object(teacher, "reader_trace", side_effect=AssertionError("trace forbidden")), patch.object(teacher, "writer_trace", side_effect=AssertionError("writer forbidden")), patch.object(type(self.gen), "read", side_effect=AssertionError("legacy reader forbidden")):
            model = fit(self.train, self.lex)
            r = model.read(self.text)
            self.assertEqual(generate(model, r["packet"], self.gen)["status"], "generated")

    def test_training_signature(self):
        params = list(inspect.signature(fit).parameters)
        self.assertEqual(params, ["pairs", "lexicon", "seed", "dimension", "pair_learning", "ordered"])

    def test_no_trace_fields_allowed(self):
        for name in ("reader_trace", "state", "actions", "order", "gold_position", "id", "metadata"):
            row = dict(self.train[0], **{name: []})
            with self.subTest(name=name), self.assertRaises(ValueError):
                fit([row], self.lex)

    def test_no_extra_meaning_fields(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["state_trace"] = []
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_pair_schema_is_only_text_meaning(self):
        self.assertTrue(all(set(row) == {"text", "meaning"} for row in self.train))
        self.assertFalse(self.reader.meta["reader_trace_supervision"])
        self.assertEqual(self.reader.meta["supervision_fields"], ["text", "meaning"])

    def test_automatically_derived_correspondences(self):
        self.assertEqual(self.reader.meta["statistics"]["support"]["contexts"], 8)
        self.assertEqual(self.reader.meta["statistics"]["roles"]["contexts"], 24)
        self.assertEqual(self.reader.meta["statistics"]["states"]["contexts"], 16)

    def test_no_marker_semantic_labels(self):
        self.assertTrue(all(t["value"] is None for t in self.lex["tokens"] if t["kind"] == "marker"))

    def test_reject_marker_semantic_labels(self):
        lex = copy.deepcopy(self.lex)
        next(t for t in lex["tokens"] if t["kind"] == "marker")["value"] = "polarity:negative"
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_roles_follow_counterfactual_supervision(self):
        train, lex = transform(self.train, self.lex, "roles_swapped")
        model = fit(train, lex)
        expected = interpret(self.text)
        expected["subject"], expected["object"] = expected["object"], expected["subject"]
        self.assertEqual(model.recover(model.read(self.text)["packet"])["slots"], expected)

    def test_states_follow_counterfactual_supervision(self):
        train, lex = transform(self.train, self.lex, "states_flipped")
        model = fit(train, lex)
        slots = model.recover(model.read(self.text)["packet"])["slots"]
        self.assertEqual(slots["polarity"], "polarity:negative")
        self.assertEqual(slots["modality"], "modality:hypothetical")

    def test_opaque_markers_learned(self):
        train, lex = transform(self.train, self.lex, "markers_renamed")
        model = fit(train, lex)
        text = rename_text(self.text, marker_map(self.lex))
        self.assertEqual(model.recover(model.read(text)["packet"])["slots"], interpret(self.text))

    def test_removed_negative_examples_not_guessed(self):
        train = [r for r in self.train if r["meaning"]["polarity"] == "polarity:positive"]
        model = fit(train, self.lex)
        self.assertEqual(model.read("太郎が花子を助けなかった。")["status"], "abstain")
        self.assertEqual(model.read(self.text)["status"], "read")

    def test_no_pair_learning_keeps_lexicon_but_cannot_read(self):
        model = fit(self.train, self.lex, pair_learning=False)
        self.assertEqual(model.lexical.recall([("token", "太郎")])["value"], "entity:太郎")
        self.assertEqual(model.read(self.text)["status"], "abstain")

    def test_no_order_is_ambiguous(self):
        model = fit(self.train, self.lex, ordered=False)
        self.assertGreater(model.meta["statistics"]["roles"]["conflicting_contexts"], 0)
        self.assertEqual(model.read(self.text)["status"], "abstain")

    def test_state_memory_necessary(self):
        memories = dict(self.reader.memories)
        old = memories["states"]
        memories["states"] = Association(old.space, np.zeros(old.space.book.dimension), old.candidates)
        model = PairReader(self.reader.meta, memories, self.reader.lexical)
        self.assertEqual(model.read(self.text)["reason"], "semantic_status_unresolved")

    def test_role_memory_necessary(self):
        memories = dict(self.reader.memories)
        old = memories["roles"]
        memories["roles"] = Association(old.space, np.zeros(old.space.book.dimension), old.candidates)
        model = PairReader(self.reader.meta, memories, self.reader.lexical)
        self.assertEqual(model.read(self.text)["reason"], "role_or_lexical_association_unresolved")

    def test_ordered_shape_is_not_bag_of_words(self):
        kinds = self.reader.meta["token_kinds"]
        a = abstract(tokenize(self.text, kinds), kinds)
        b = abstract(tokenize("花子を太郎が助けた。", kinds), kinds)
        space = Space(Book())
        self.assertGreater(np.linalg.norm(space.key(descriptor(a)) - space.key(descriptor(b))), 1.)
        collapsed = Space(Book(), False)
        np.testing.assert_array_equal(collapsed.key(descriptor(a, ordered=False)), collapsed.key(descriptor(b, ordered=False)))

    def test_shape_abstracts_names_and_verbs(self):
        kinds = self.reader.meta["token_kinds"]
        self.assertEqual(abstract(tokenize(self.text, kinds), kinds), abstract(tokenize("次郎が美咲を褒めた。", kinds), kinds))

    def test_shapes_learned_not_preinstalled(self):
        train = [r for r in self.train if not r["text"].startswith("もし")]
        model = fit(train, self.lex)
        self.assertEqual(model.read("もし太郎が花子を助けたら。")["status"], "abstain")

    def test_paraphrases_same_meaning(self):
        other = self.reader.read("花子を太郎が助けた。")["packet"]
        np.testing.assert_allclose(self.reader.unpack(self.packet), self.reader.unpack(other), atol=1e-12)

    def test_swapped_entities_differ(self):
        other = self.reader.read("花子が太郎を助けた。")["packet"]
        self.assertGreater(np.linalg.norm(self.reader.unpack(self.packet) - self.reader.unpack(other)), 1.)

    def test_negative_hypothetical(self):
        packet = self.reader.read("もし太郎が花子を助けなかったら。")["packet"]
        out = generate(self.reader, packet, self.gen)
        self.assertEqual(out["text"], "もし花子を太郎が助けなかったら。")

    def test_self_reference_inference(self):
        read = self.reader.read("太郎が太郎を助けた。")
        self.assertEqual(read["status"], "read")
        slots = self.reader.recover(read["packet"])["slots"]
        self.assertEqual(slots["subject"], slots["object"])

    def test_ambiguous_training_alignment_rejected(self):
        row = {"text": "太郎が太郎を助けた。", "meaning": interpret("太郎が太郎を助けた。")}
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_missing_alignment_rejected(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["predicate"] = "predicate:gaze_at" if row["meaning"]["predicate"] != "predicate:gaze_at" else "predicate:help"
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_contradictory_duplicate_rejected(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["subject"], row["meaning"]["object"] = row["meaning"]["object"], row["meaning"]["subject"]
        with self.assertRaises(ValueError):
            fit([self.train[0], row], self.lex)

    def test_training_order_determinism(self):
        model = fit(list(reversed(self.train)), self.lex)
        self.assertEqual(model.fingerprint, self.reader.fingerprint)

    def test_training_no_source_sentence_in_model_metadata(self):
        serial = canonical(self.reader.meta)
        for row in self.train:
            self.assertNotIn(row["text"], serial)
        self.assertNotIn("read_action", serial)
        self.assertNotIn("read_next", serial)

    def test_invalid_inputs(self):
        for text in INVALID:
            with self.subTest(text=text):
                self.assertEqual(self.reader.read(text)["status"], "abstain")

    def test_nonstring_input(self):
        for value in (None, {}, [], True, 1):
            self.assertEqual(self.reader.read(value)["status"], "abstain")

    def test_packet_has_no_gold(self):
        self.assertEqual(set(self.packet), {"schema", "reader_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        self.assertNotIn("太郎", canonical(self.packet))

    def test_extra_packet_fields(self):
        for field in ("text", "meaning", "gold", "trace", "metadata", "order"):
            self.assertEqual(self.reader.recover(dict(self.packet, **{field: []}))["status"], "abstain")

    def test_nonfinite_packet(self):
        for value in (float("nan"), float("inf"), True, "1", 1e100):
            packet = copy.deepcopy(self.packet)
            packet["real"][0] = value
            self.assertEqual(self.reader.recover(packet)["status"], "abstain")

    def test_wrong_packet_identity(self):
        self.assertEqual(self.reader.recover(dict(self.packet, reader_fingerprint="bad"))["status"], "abstain")

    def test_wrong_packet_dimension(self):
        self.assertEqual(self.reader.recover(dict(self.packet, dimension=2))["status"], "abstain")

    def test_inference_disabled(self):
        self.assertEqual(self.reader.recover(dict(self.packet, eligible_for_inference=True))["status"], "abstain")
        self.assertFalse(self.reader.read(self.text)["eligible_for_inference"])

    def test_zero_packet(self):
        packet = self.reader.pack(np.zeros(self.reader.book.dimension, dtype=complex))
        self.assertEqual(self.reader.recover(packet)["status"], "abstain")

    def test_interference_packet(self):
        vector = self.reader.unpack(self.packet) + self.reader.book.code("noise", "unrelated")
        self.assertEqual(self.reader.recover(self.reader.pack(vector))["status"], "abstain")

    def test_bridge_no_text_or_labels(self):
        bridged = translate(self.reader, self.packet, self.gen)
        self.assertEqual(bridged["status"], "bridged")
        self.assertEqual(set(bridged["packet"]), {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        self.assertEqual(self.gen.recover(bridged["packet"])["slots"], interpret(self.text))

    def test_bridge_preserves_generator_fingerprint(self):
        before = self.gen.fingerprint
        generate(self.reader, self.packet, self.gen)
        self.assertEqual(before, self.gen.fingerprint)
        self.assertEqual(before, generator().fingerprint)

    def test_bridge_refuses_bad_signal(self):
        self.assertEqual(translate(self.reader, {}, self.gen)["status"], "abstain")

    def test_unknown_generation_goal(self):
        self.assertEqual(generate(self.reader, self.packet, self.gen, "essay")["status"], "abstain")

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as directory:
            self.reader.save(directory)
            loaded = PairReader.load(directory)
            self.assertEqual(loaded.fingerprint, self.reader.fingerprint)
            self.assertEqual(loaded.read(self.text)["packet"], self.packet)

    def test_save_overwrite_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            self.reader.save(directory)
            with self.assertRaises(ValueError):
                self.reader.save(directory)

    def test_model_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.reader.save(directory)
            path = Path(directory) / "reader.json"
            info = json.loads(path.read_text(encoding="utf-8"))
            info["metadata"]["pair_count"] += 1
            path.write_text(json.dumps(info), encoding="utf-8")
            with self.assertRaises(ValueError):
                PairReader.load(directory)

    def test_invalid_dimension(self):
        with self.assertRaises(ValueError):
            fit(self.train, self.lex, dimension=129)

    def test_empty_pairs(self):
        with self.assertRaises(ValueError):
            fit([], self.lex)

    def test_type_validation(self):
        with self.assertRaises(ValueError):
            fit(self.train, self.lex, ordered=1)

    def test_pair_partition_disjoint(self):
        keys = lambda rows: {(r["meaning"]["subject"], r["meaning"]["object"], r["meaning"]["predicate"]) for r in rows}
        a, b, c = keys(self.train), keys(self.dev), keys(load_data("evaluation"))
        self.assertFalse(a & b or a & c or b & c)

    def test_ordinary_lookup_control(self):
        model = LookupReader(self.train, self.lex)
        for row in self.dev:
            self.assertEqual(model.read(row["text"]), row["meaning"])

    def test_learner_source_does_not_import_teacher_generator_or_oracle(self):
        import plm_l1_v02.training as training
        import plm_l1_v02.runtime as runtime
        for module in (training, runtime):
            code = inspect.getsource(module)
            self.assertNotIn("import plm_l1.teacher", code)
            self.assertNotIn("from plm_l1.teacher", code)
            self.assertNotIn("from evaluation_support", code)
            self.assertNotIn("import generator", code)
            for literal in ("太郎", "花子", "もし", "なかった", '"が"', '"を"'):
                self.assertNotIn(literal, code)


if __name__ == "__main__":
    unittest.main()
