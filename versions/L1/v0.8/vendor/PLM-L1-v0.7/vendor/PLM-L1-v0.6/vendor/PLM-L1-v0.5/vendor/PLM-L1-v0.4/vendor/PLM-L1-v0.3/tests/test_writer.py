import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v03.algebra import Book, canonical
from plm_l1_v03.features import aligned_examples, Space, GOALS, END
from plm_l1_v03.training import fit
from plm_l1_v03.runtime import Writer
from plm_l1_v03.memory import Association
from plm_l1_v03.bridge import fixed_reader, translate
from evaluation_support import data, oracle, transform, score, LookupWriter
from evaluate import bad_packets


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train, cls.dev, cls.lex = data("train"), data("development"), data("lexicon")
        cls.writer = fit(cls.train, cls.lex)
        cls.reader = fixed_reader()
        interpret, invalid, patterns = oracle()
        cls.interpret, cls.invalid, cls.patterns = staticmethod(interpret), invalid, patterns
        cls.text = "太郎が花子を助けた。"
        cls.meaning = interpret(cls.text)
        cls.packet = cls.writer.encode(cls.meaning)

    def test_standalone_all_development(self):
        for row in self.dev:
            packet = self.writer.encode(row["meaning"])
            for goal in GOALS:
                out = self.writer.generate(packet, goal)
                s = score(out["text"], row["meaning"], goal, "full", self.interpret, self.patterns)
                self.assertEqual(out["status"], "generated")
                self.assertTrue(s["meaning_exact"] and s["goal_exact"])

    def test_fixed_reader_roundtrips_all_development(self):
        for row in self.dev:
            reading = self.reader.read(row["text"])
            packet = translate(self.reader, reading["packet"], self.writer)["packet"]
            for goal in GOALS:
                out = self.writer.generate(packet, goal)
                self.assertEqual(self.interpret(out["text"]), row["meaning"])

    def test_no_legacy_teacher_reader_or_generator_used(self):
        import plm_l1.teacher as teacher
        from plm_l1.runtime import Model
        with patch.object(teacher, "reader_trace", side_effect=AssertionError("forbidden")), patch.object(teacher, "writer_trace", side_effect=AssertionError("forbidden")), patch.object(Model, "generate", side_effect=AssertionError("forbidden")), patch.object(Model, "read", side_effect=AssertionError("forbidden")), patch.object(type(self.reader), "read", side_effect=AssertionError("forbidden")):
            model = fit(self.train, self.lex)
            self.assertEqual(model.generate(model.encode(self.meaning))["text"], "花子を太郎が助けた。")

    def test_fit_api_fields(self):
        self.assertEqual(list(inspect.signature(fit).parameters), ["pairs", "lexicon", "seed", "dimension", "pair_learning", "use_prefix", "use_status"])
        for field in ("actions", "states", "trace", "reader_trace", "writer_trace", "order", "goal", "id", "token_roles"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                fit([dict(self.train[0], **{field: []})], self.lex)

    def test_automatic_alignment_and_stop(self):
        examples = aligned_examples(self.train, self.lex)
        self.assertEqual(len(examples), 576)
        self.assertEqual({r["goal"] for r in examples}, set(GOALS))
        self.assertTrue(all(len(r["sequence"]) in (7, 8) for r in examples))
        self.assertIn(END, self.writer.memories["steps"].candidates)
        self.assertFalse(self.writer.meta["supplied_trace_supervision"])
        self.assertEqual(self.writer.meta["statistics"]["steps"]["contexts"], 68)

    def test_no_marker_meanings(self):
        self.assertTrue(all(t["value"] is None for t in self.lex["tokens"] if t["kind"] == "marker"))
        lex = copy.deepcopy(self.lex)
        next(t for t in lex["tokens"] if t["kind"] == "marker")["value"] = "polarity:negative"
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_conflicting_duplicate_text(self):
        other = copy.deepcopy(self.train[0])
        other["meaning"]["polarity"] = "polarity:negative" if other["meaning"]["polarity"] == "polarity:positive" else "polarity:positive"
        with self.assertRaises(ValueError):
            fit([self.train[0], other], self.lex)

    def test_ambiguous_alignment(self):
        row = {"text": "太郎が太郎を助けた。", "meaning": self.interpret("太郎が太郎を助けた。")}
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_missing_alignment(self):
        row = copy.deepcopy(self.train[0])
        row["meaning"]["predicate"] = "predicate:gaze_at" if row["meaning"]["predicate"] != "predicate:gaze_at" else "predicate:help"
        with self.assertRaises(ValueError):
            fit([row], self.lex)

    def test_unknown_training_word(self):
        with self.assertRaises(ValueError):
            fit([{"text": "未知が花子を助けた。", "meaning": self.meaning}], self.lex)

    def test_extra_meaning_field(self):
        with self.assertRaises(ValueError):
            self.writer.encode(dict(self.meaning, state="S0"))

    def test_unknown_meaning(self):
        with self.assertRaises(ValueError):
            self.writer.encode(dict(self.meaning, subject="entity:未知"))

    def test_duplicate_surface(self):
        lex = copy.deepcopy(self.lex)
        lex["tokens"].append(copy.deepcopy(lex["tokens"][0]))
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_ambiguous_lexical_realization(self):
        lex = copy.deepcopy(self.lex)
        token = copy.deepcopy(next(t for t in lex["tokens"] if t["kind"] == "entity"))
        token["surface"] = "別名"
        lex["tokens"].append(token)
        with self.assertRaises(ValueError):
            fit(self.train, lex)

    def test_balanced_duplicates(self):
        model = fit(self.train + self.train, self.lex)
        for name in self.writer.memories:
            np.testing.assert_array_equal(model.memories[name].vector, self.writer.memories[name].vector)

    def test_order_determinism(self):
        self.assertEqual(fit(list(reversed(self.train)), self.lex).fingerprint, self.writer.fingerprint)

    def test_no_full_sentences_or_context_tables_saved(self):
        serial = canonical(self.writer.meta)
        self.assertTrue(all(r["text"] not in serial for r in self.train))
        for memory in self.writer.memories.values():
            self.assertFalse(hasattr(memory, "groups"))
            self.assertTrue(all(r["text"] not in canonical(memory.candidates) for r in self.train))

    def test_no_pair_learning_keeps_lexicon(self):
        model = fit(self.train, self.lex, pair_learning=False)
        self.assertEqual(model.memories["lexical"].recall({"lexical_value": "entity:太郎"})["value"], "太郎")
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "abstain")

    def test_no_prefix_is_ambiguous(self):
        model = fit(self.train, self.lex, use_prefix=False)
        self.assertGreater(model.meta["statistics"]["steps"]["conflicting_contexts"], 0)
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "abstain")

    def test_no_status_is_ambiguous(self):
        model = fit(self.train, self.lex, use_status=False)
        self.assertGreater(model.meta["statistics"]["steps"]["conflicting_contexts"], 0)
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "abstain")

    def test_roles_follow_teacher_change(self):
        rows, lex = transform(self.train, self.lex, "roles_swapped")
        model = fit(rows, lex)
        out = model.generate(model.encode(self.meaning))
        self.assertEqual(out["text"], "花子が太郎を助けた。")
        self.assertTrue(score(out["text"], self.meaning, "object", "roles_swapped", self.interpret, self.patterns)["meaning_exact"])

    def test_states_follow_teacher_change(self):
        rows, lex = transform(self.train, self.lex, "states_flipped")
        model = fit(rows, lex)
        self.assertEqual(model.generate(model.encode(self.meaning))["text"], "もし花子を太郎が助けなかったら。")

    def test_opaque_markers(self):
        rows, lex = transform(self.train, self.lex, "markers_renamed")
        model = fit(rows, lex)
        out = model.generate(model.encode(self.meaning))
        self.assertIn("~M", out["text"])
        self.assertTrue(score(out["text"], self.meaning, "object", "markers_renamed", self.interpret, self.patterns)["meaning_exact"])

    def test_withheld_negative_abstains(self):
        model = fit([r for r in self.train if r["meaning"]["polarity"] == "polarity:positive"], self.lex)
        self.assertEqual(model.generate(model.encode(self.meaning))["status"], "generated")
        self.assertEqual(model.generate(model.encode(dict(self.meaning, polarity="polarity:negative")))["status"], "abstain")

    def test_withheld_style_not_preinstalled(self):
        pairs = [r for r, e in zip(self.train, aligned_examples(self.train, self.lex)) if e["goal"] == "subject"]
        model = fit(pairs, self.lex)
        self.assertEqual(model.generate(model.encode(self.meaning), "object")["status"], "abstain")
        self.assertEqual(model.generate(model.encode(self.meaning), "subject")["text"], self.text)

    def test_prefix_order_is_not_commutative(self):
        space = Space(Book())
        a = space.context(self.meaning, "subject", ["a", "b"])
        b = space.context(self.meaning, "subject", ["b", "a"])
        self.assertGreater(np.linalg.norm(space.key(a) - space.key(b)), 1.)

    def test_prefix_abstracts_content_values(self):
        space = Space(Book())
        a = space.context(self.meaning, "subject", [canonical(["slot", "subject"])])
        other = dict(self.meaning, subject="entity:次郎")
        self.assertEqual(a, space.context(other, "subject", a["prefix"]))

    def test_role_bound_signals_differ(self):
        other = self.writer.encode(dict(self.meaning, subject=self.meaning["object"], object=self.meaning["subject"]))
        self.assertNotEqual(other["real"], self.packet["real"])

    def test_packet_contains_only_signal(self):
        self.assertEqual(set(self.packet), {"schema", "writer_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        self.assertNotIn("太郎", canonical(self.packet))

    def test_invalid_packets(self):
        for i, packet in enumerate(bad_packets(self.writer, self.meaning)):
            with self.subTest(case=i):
                self.assertEqual(self.writer.generate(packet)["status"], "abstain")

    def test_more_packet_extra_fields(self):
        for field in ("gold", "trace", "actions", "source", "goal", "metadata"):
            self.assertEqual(self.writer.generate(dict(self.packet, **{field: []}))["status"], "abstain")

    def test_packet_nonobjects(self):
        for value in (None, [], "text", 1, True):
            self.assertEqual(self.writer.generate(value)["status"], "abstain")

    def test_mismatched_signal_lengths(self):
        self.assertEqual(self.writer.generate(dict(self.packet, real=self.packet["real"][:-1]))["status"], "abstain")

    def test_unknown_goal(self):
        for goal in ("essay", None, [], True):
            self.assertEqual(self.writer.generate(self.packet, goal)["status"], "abstain")

    def test_step_budget(self):
        self.assertEqual(self.writer.generate(self.packet, max_steps=1)["reason"], "step_budget_exhausted")
        self.assertIsNone(self.writer.generate(self.packet, max_steps=1)["text"])
        for budget in (0, 65, True):
            self.assertEqual(self.writer.generate(self.packet, max_steps=budget)["status"], "abstain")

    def test_premature_stop_guard(self):
        with patch.object(self.writer.memories["steps"], "recall", return_value={"value": END}):
            self.assertEqual(self.writer.generate(self.packet)["reason"], "premature_end")

    def test_repeated_role_guard(self):
        with patch.object(self.writer.memories["steps"], "recall", return_value={"value": canonical(["slot", "object"])}):
            self.assertEqual(self.writer.generate(self.packet)["reason"], "invalid_role_emission")

    def test_missing_stop_bounded(self):
        with patch.object(self.writer.memories["steps"], "recall", return_value={"value": canonical(["literal", "。"]) }):
            self.assertEqual(self.writer.generate(self.packet)["reason"], "output_capacity_exceeded")

    def test_lexical_memory_required(self):
        memories = dict(self.writer.memories)
        old = memories["lexical"]
        memories["lexical"] = Association(old.space, np.zeros(old.space.book.dimension), old.candidates)
        model = Writer(self.writer.meta, memories)
        self.assertEqual(model.generate(model.encode(self.meaning))["reason"], "lexical_realization_unresolved")

    def test_self_reference_generation(self):
        meaning = dict(self.meaning, object=self.meaning["subject"])
        self.assertEqual(self.writer.generate(self.writer.encode(meaning))["text"], "太郎を太郎が助けた。")

    def test_negative_hypothetical(self):
        meaning = dict(self.meaning, polarity="polarity:negative", modality="modality:hypothetical")
        self.assertEqual(self.writer.generate(self.writer.encode(meaning))["text"], "もし花子を太郎が助けなかったら。")

    def test_reading_signal_bridge(self):
        reading = self.reader.read(self.text)
        bridged = translate(self.reader, reading["packet"], self.writer)
        self.assertEqual(self.writer.recover(bridged["packet"])["meaning"], self.meaning)
        self.assertEqual(translate(self.reader, {}, self.writer)["status"], "abstain")

    def test_fixed_reader_unchanged(self):
        self.assertEqual(self.reader.fingerprint, fixed_reader().fingerprint)
        self.assertEqual(self.reader.fingerprint, "fd7635ee535b265995c3e95d22f01493b2216472fe9e1e7976104a666a32bec1")

    def test_invalid_read_inputs(self):
        for text in self.invalid:
            self.assertEqual(self.reader.read(text)["status"], "abstain")

    def test_inference_remains_disabled(self):
        self.assertFalse(self.packet["eligible_for_inference"])
        self.assertFalse(self.writer.generate(self.packet)["eligible_for_inference"])

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            model = Writer.load(temp)
            self.assertEqual(model.fingerprint, self.writer.fingerprint)
            self.assertEqual(model.generate(self.packet), self.writer.generate(self.packet))

    def test_save_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            with self.assertRaises(ValueError):
                self.writer.save(temp)

    def test_metadata_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            path = Path(temp) / "writer.json"
            info = json.loads(path.read_text(encoding="utf-8"))
            info["metadata"]["pair_count"] += 1
            path.write_text(json.dumps(info), encoding="utf-8")
            with self.assertRaises(ValueError):
                Writer.load(temp)

    def test_weights_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            self.writer.save(temp)
            path = Path(temp) / "weights.npz"
            with np.load(path, allow_pickle=False) as weights:
                arrays = {k: weights[k] for k in weights.files}
            arrays["steps"][0] += 1
            np.savez_compressed(path, **arrays)
            with self.assertRaises(ValueError):
                Writer.load(temp)

    def test_invalid_fit_configuration(self):
        for kwargs in ({"dimension": 129}, {"use_prefix": 1}, {"seed": ""}):
            with self.assertRaises(ValueError):
                fit(self.train, self.lex, **kwargs)
        with self.assertRaises(ValueError):
            fit([], self.lex)

    def test_composition_split_disjoint(self):
        keys = lambda rows: {(r["meaning"]["subject"], r["meaning"]["object"], r["meaning"]["predicate"]) for r in rows}
        a, b, c = keys(self.train), keys(self.dev), keys(data("evaluation"))
        self.assertFalse(a & b or a & c or b & c)

    def test_ordinary_reference(self):
        model = LookupWriter(self.train, self.lex)
        for row in self.dev:
            for goal in GOALS:
                out = model.generate(row["meaning"], goal)
                self.assertEqual(self.interpret(out), row["meaning"])

    def test_core_has_no_language_or_legacy_imports(self):
        from plm_l1_v03 import training, runtime, features, memory
        for module in (training, runtime, features, memory):
            code = inspect.getsource(module)
            for text in ("from plm_l1.", "from plm_l1_v02", "import teacher", "from evaluation_support", "太郎", "花子", "もし", "なかった", '"が"', '"を"'):
                self.assertNotIn(text, code)


if __name__ == "__main__":
    unittest.main()
