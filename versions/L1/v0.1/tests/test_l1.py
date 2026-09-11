import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from plm_l1.algebra import Book, Memory, learn
from plm_l1.training import fit
from plm_l1.runtime import Model, reader_key, writer_key, chip_roundtrip
from plm_l1.teacher import examples, lexicon
from plm_l1.oracle import interpret, INVALID


class AlgebraTests(unittest.TestCase):
    def test_deterministic(self):
        np.testing.assert_array_equal(Book().code("x", "a"), Book().code("x", "a"))

    def test_unit_phasors(self):
        np.testing.assert_allclose(np.abs(Book().code("x", "a")), 1., atol=1e-14)

    def test_inverse_binding(self):
        b = Book()
        x, y = b.code("x", "a"), b.code("y", "b")
        np.testing.assert_allclose(x * y * y.conj(), x, atol=1e-14)

    def test_namespace_separation(self):
        b = Book()
        self.assertLess(abs(np.mean(b.code("x", "a") * b.code("y", "a").conj())), .1)

    def test_dimension_validation(self):
        for d in (0, 127, 129, 32768, True, 128.):
            with self.subTest(d=d), self.assertRaises(ValueError):
                Book(d)

    def test_seed_validation(self):
        for seed in ("", None, "a" * 129):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                Book(seed=seed)

    def test_hebbian_association(self):
        pairs = [([("key", str(i))], str(i)) for i in range(20)]
        memory, stats = learn(Book(), pairs)
        self.assertEqual(stats["contexts"], 20)
        for parts, target in pairs:
            self.assertEqual(memory.recall(parts)["value"], target)

    def test_unknown_association_abstains(self):
        memory, _ = learn(Book(), [([("key", "a")], "one"), ([("key", "b")], "two")])
        self.assertIsNone(memory.recall([("key", "missing")])["value"])

    def test_no_learning(self):
        memory, _ = learn(Book(), [([("key", "a")], "one")], False)
        self.assertIsNone(memory.recall([("key", "a")])["value"])

    def test_conflicting_associations_abstain(self):
        memory, stats = learn(Book(), [([("key", "a")], "one"), ([("key", "a")], "two")])
        self.assertEqual(stats["conflicting_contexts"], 1)
        self.assertIsNone(memory.recall([("key", "a")])["value"])

    def test_order_ablation_removes_state(self):
        self.assertNotEqual(reader_key("q1", "X"), reader_key("q2", "X"))
        self.assertEqual(reader_key("q1", "X", False), reader_key("q2", "X", False))

    def test_order_ablation_removes_position(self):
        self.assertNotEqual(writer_key("x", 0, "p", "m"), writer_key("x", 1, "p", "m"))
        self.assertEqual(writer_key("x", 0, "p", "m", False), writer_key("x", 1, "p", "m", False))


class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = fit()
        cls.sample = "太郎が花子を助けた。"
        cls.packet = cls.model.read(cls.sample)["packet"]

    def test_all_development_readings_and_both_goals(self):
        for example in examples("development"):
            with self.subTest(id=example["id"]):
                read = self.model.read(example["text"])
                self.assertEqual(read["status"], "read")
                self.assertEqual(self.model.recover(read["packet"])["slots"], example["slots"])
                for goal in self.model.meta["goals"]:
                    generated = self.model.generate(read["packet"], goal)
                    self.assertEqual(generated["status"], "generated")
                    self.assertEqual(interpret(generated["text"]), example["slots"])

    def test_role_swaps_change_packet(self):
        other = self.model.read("花子が太郎を助けた。")["packet"]
        self.assertNotEqual(other["real"], self.packet["real"])

    def test_paraphrases_same_meaning_signal(self):
        other = self.model.read("花子を太郎が助けた。")["packet"]
        np.testing.assert_allclose(other["real"], self.packet["real"], atol=1e-14)
        np.testing.assert_allclose(other["imag"], self.packet["imag"], atol=1e-14)

    def test_negative_not_phase_sign_flip(self):
        other = self.model.read("太郎が花子を助けなかった。")["packet"]
        self.assertGreater(np.linalg.norm(self.model.unpack(other) + self.model.unpack(self.packet)), 1.)
        self.assertEqual(self.model.recover(other)["slots"]["polarity"], "polarity:negative")

    def test_hypothetical_not_asserted(self):
        packet = self.model.read("もし太郎が花子を助けたら。")["packet"]
        self.assertEqual(self.model.recover(packet)["slots"]["modality"], "modality:hypothetical")

    def test_negative_hypothetical(self):
        packet = self.model.read("もし太郎が花子を助けなかったら。")["packet"]
        self.assertEqual(self.model.generate(packet)["text"], "もし花子を太郎が助けなかったら。")

    def test_invalid_inputs(self):
        for text in INVALID:
            with self.subTest(text=text):
                self.assertIsNone(interpret(text))
                self.assertEqual(self.model.read(text)["status"], "abstain")

    def test_nontext_input(self):
        for value in (None, 2, {}, [], True):
            self.assertEqual(self.model.read(value)["status"], "abstain")

    def test_repeated_roles_rejected(self):
        self.assertEqual(self.model.read("太郎が花子が助けた。")["status"], "abstain")

    def test_unseen_self_pair_is_not_a_new_entity(self):
        result = self.model.read("太郎が太郎を助けた。")
        self.assertEqual(result["status"], "read")
        decoded = self.model.recover(result["packet"])["slots"]
        self.assertEqual(decoded["subject"], decoded["object"])

    def test_packet_contains_no_text_or_slots(self):
        self.assertEqual(set(self.packet), {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"})
        serial = json.dumps(self.packet, ensure_ascii=False)
        self.assertNotIn(self.sample, serial)
        self.assertNotIn("太郎", serial)

    def test_extra_packet_fields_rejected(self):
        for name in ("text", "slots", "gold", "metadata", "source", "trace"):
            packet = dict(self.packet, **{name: "forbidden"})
            self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_wrong_model_packet(self):
        packet = dict(self.packet, model_fingerprint="0" * 64)
        self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_wrong_schema(self):
        self.assertEqual(self.model.generate(dict(self.packet, schema="unknown"))["status"], "abstain")

    def test_inference_flag(self):
        self.assertFalse(self.model.read(self.sample)["eligible_for_inference"])
        self.assertFalse(self.model.generate(self.packet)["eligible_for_inference"])
        self.assertEqual(self.model.generate(dict(self.packet, eligible_for_inference=True))["status"], "abstain")

    def test_wrong_signal_shape(self):
        self.assertEqual(self.model.generate(dict(self.packet, real=[0.]))["status"], "abstain")

    def test_invalid_signal_numbers(self):
        for value in (float("nan"), float("inf"), True, "1", 1e100):
            packet = copy.deepcopy(self.packet)
            packet["real"][0] = value
            self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_zero_signal(self):
        packet = self.model.pack(np.zeros(self.model.book.dimension, dtype=complex))
        self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_excess_interference(self):
        packet = self.model.pack(self.model.unpack(self.packet) + self.model.book.code("noise", "unrelated"))
        self.assertEqual(self.model.generate(packet)["status"], "abstain")

    def test_unknown_goal(self):
        self.assertEqual(self.model.generate(self.packet, "essay")["status"], "abstain")

    def test_generation_signature_has_no_source(self):
        self.assertEqual(list(inspect.signature(Model.generate).parameters), ["self", "packet", "goal"])

    def test_runtime_does_not_import_teacher_or_oracle(self):
        import plm_l1.runtime as runtime
        code = inspect.getsource(runtime)
        self.assertNotIn("from .teacher", code)
        self.assertNotIn("from .oracle", code)
        for word in ("太郎", "花子", "もし", "なかった", "subject_first", "object_first"):
            if word != "object_first":
                self.assertNotIn(word, code)

    def test_model_save_load_and_readonly_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            loaded = Model.load(directory)
            self.assertEqual(loaded.fingerprint, self.model.fingerprint)
            self.assertEqual(loaded.generate(self.packet)["text"], "花子を太郎が助けた。")
            with self.assertRaises(ValueError):
                self.model.save(directory)

    def test_model_tamper_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            path = Path(directory) / "model.json"
            info = json.loads(path.read_text(encoding="utf-8"))
            info["metadata"]["training_count"] += 1
            path.write_text(json.dumps(info), encoding="utf-8")
            with self.assertRaises(ValueError):
                Model.load(directory)

    def test_no_learning_ablation(self):
        self.assertEqual(fit(learning=False).read(self.sample)["status"], "abstain")

    def test_no_order_ablation(self):
        model = fit(order_binding=False)
        self.assertGreater(model.meta["memory_statistics"]["read_next"]["conflicting_contexts"], 0)
        self.assertEqual(model.read(self.sample)["status"], "abstain")

    def test_no_role_ablation(self):
        model = fit(role_binding=False)
        read = model.read(self.sample)
        self.assertEqual(read["status"], "read")
        self.assertEqual(model.generate(read["packet"])["status"], "abstain")

    def test_generation_learning_needed_even_with_working_reader(self):
        memories = dict(self.model.memories)
        old = memories["write_action"]
        memories["write_action"] = Memory(old.book, np.zeros(old.book.dimension), old.candidates)
        model = Model(self.model.meta, memories)
        read = model.read(self.sample)
        self.assertEqual(read["status"], "read")
        self.assertEqual(model.generate(read["packet"])["reason"], "generation_memory_unresolved")

    def test_reverse_lexical_learning_needed(self):
        memories = dict(self.model.memories)
        old = memories["surface"]
        memories["surface"] = Memory(old.book, np.zeros(old.book.dimension), old.candidates)
        model = Model(self.model.meta, memories)
        read = model.read(self.sample)
        self.assertEqual(read["status"], "read")
        self.assertEqual(model.generate(read["packet"])["reason"], "surface_memory_unresolved")

    def test_state_learning_needed(self):
        memories = dict(self.model.memories)
        old = memories["read_next"]
        memories["read_next"] = Memory(old.book, np.zeros(old.book.dimension), old.candidates)
        model = Model(self.model.meta, memories)
        self.assertEqual(model.read(self.sample)["reason"], "grammar_memory_unresolved")

    def test_chip_mapping_preserves_energy_and_meaning(self):
        packet, audit = chip_roundtrip(self.model, self.packet)
        self.assertAlmostEqual(audit["input_energy"], audit["chip_energy"], places=8)
        self.assertLess(audit["maximum_error"], 1e-12)
        self.assertEqual(self.model.generate(packet)["text"], "花子を太郎が助けた。")

    def test_invalid_chip_length(self):
        for length in (1, 3, 0, 128, True):
            with self.subTest(length=length), self.assertRaises(ValueError):
                chip_roundtrip(self.model, self.packet, length)

    def test_partition_is_disjoint_by_composition(self):
        partitions = {}
        for split in ("train", "development", "evaluation"):
            rows = list(examples(split))
            partitions[split] = {(x["slots"]["subject"], x["slots"]["object"], x["slots"]["predicate"]) for x in rows}
        self.assertFalse(partitions["train"] & partitions["evaluation"])
        self.assertFalse(partitions["train"] & partitions["development"])
        self.assertFalse(partitions["development"] & partitions["evaluation"])

    def test_teacher_and_independent_oracle_agree_on_development(self):
        for example in examples("development"):
            self.assertEqual(interpret(example["text"]), example["slots"])

    def test_fixed_identity_and_fitted_memory_separate(self):
        blank = fit(learning=False)
        np.testing.assert_array_equal(blank.book.code("value", "entity:太郎"), self.model.book.code("value", "entity:太郎"))
        self.assertFalse(np.array_equal(blank.memories["read_action"].vector, self.model.memories["read_action"].vector))


if __name__ == "__main__":
    unittest.main()
