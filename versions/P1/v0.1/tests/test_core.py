from copy import deepcopy
from dataclasses import replace
import os
import subprocess
import sys
import unittest
import numpy as np
from plm_p1 import PhaseCodebook, encode, decode, symbol, address, DecodePolicy
from plm_p1.core import channel, validate_frames, canonical
from plm_p1.fixtures import make_frames, entity_candidates
from plm_p1.evaluation import structural_ablations, PROTOCOL


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.book = PhaseCodebook(2048, "test-core")
        self.frames = make_frames(2)
        self.candidates = entity_candidates()
        self.samples = encode(self.frames, self.book)

    def query(self, samples=None, **kwargs):
        frame = self.frames[0]
        return decode(self.samples if samples is None else samples, self.book, frame["document_id"],
                      frame["event_id"], "subject", self.candidates, **kwargs)

    def test_unit_magnitude(self):
        np.testing.assert_allclose(np.abs(self.book.value(self.candidates[0])), 1, atol=1e-14)

    def test_nontrivial_complex_phase(self):
        code = self.book.value(self.candidates[0])
        self.assertGreater(np.std(code.imag), .5)
        self.assertGreater(np.std(code.real), .5)

    def test_same_spec_reproducible(self):
        other = PhaseCodebook(2048, "test-core")
        np.testing.assert_array_equal(self.book.value(self.candidates[0]), other.value(self.candidates[0]))

    def test_dimension_prefix_stable(self):
        other = PhaseCodebook(512, "test-core")
        np.testing.assert_array_equal(self.book.value(self.candidates[0])[:512], other.value(self.candidates[0]))

    def test_seed_changes_codes(self):
        self.assertFalse(np.array_equal(self.book.value(self.candidates[0]), PhaseCodebook(2048, "other").value(self.candidates[0])))

    def test_namespace_separation(self):
        self.assertFalse(np.array_equal(self.book.code("role", "x"), self.book.code("event", "x")))

    def test_local_identity_separation(self):
        self.assertFalse(np.array_equal(self.book.value(symbol("entity", "A", "doc1")), self.book.value(symbol("entity", "A", "doc2"))))

    def test_concept_and_entity_separation(self):
        self.assertFalse(np.array_equal(self.book.value(symbol("entity", "DOG")), self.book.value(symbol("concept", "DOG"))))

    def test_cache_not_mutable_through_return_value(self):
        value = self.book.value(self.candidates[0])
        original = value.copy()
        value[:] = 0
        np.testing.assert_array_equal(original, self.book.value(self.candidates[0]))

    def test_address_delimiters_cannot_collide(self):
        self.assertNotEqual(address("a:b", "c"), address("a", "b:c"))

    def test_quasi_orthogonal_not_identical(self):
        codes = np.array([self.book.value(c) for c in self.candidates[:32]])
        gram = np.real(codes @ codes.conj().T) / self.book.dimension
        off = gram - np.eye(len(codes))
        self.assertLess(float(np.max(np.abs(off))), .1)

    def test_exact_single_binding_inverse(self):
        key = self.book.key("doc", "event", "subject")
        value = self.book.value(self.candidates[0])
        np.testing.assert_allclose(key * value * np.conj(key), value, atol=1e-14)

    def test_all_roles_roundtrip(self):
        for frame in self.frames:
            for role, truth in frame["slots"].items():
                choices = [truth, symbol(truth["kind"], "wrong", truth["scope"])]
                result = decode(self.samples, self.book, frame["document_id"], frame["event_id"], role, choices)
                self.assertEqual(result["selected"], truth)
                self.assertFalse(result["eligible_for_inference"])

    def test_role_swap_changes_recovery(self):
        swapped = deepcopy(self.frames)
        frame = swapped[0]
        frame["slots"]["subject"], frame["slots"]["object"] = frame["slots"]["object"], frame["slots"]["subject"]
        self.assertEqual(self.query(encode(swapped, self.book))["selected"], self.frames[0]["slots"]["object"])

    def test_two_dogs_are_distinct(self):
        self.assertEqual(self.frames[0]["metadata"]["subject_concept"], self.frames[0]["metadata"]["object_concept"])
        self.assertNotEqual(self.frames[0]["slots"]["subject"], self.frames[0]["slots"]["object"])
        self.assertEqual(self.query()["selected"], self.frames[0]["slots"]["subject"])

    def test_reordering_has_identical_encoding(self):
        changed = list(reversed(deepcopy(self.frames)))
        for frame in changed:
            frame["slots"] = dict(reversed(list(frame["slots"].items())))
        np.testing.assert_array_equal(encode(changed, self.book), self.samples)

    def test_partial_coordinate_recovery(self):
        mask = np.zeros(2048, dtype=bool)
        mask[::4] = True
        self.assertEqual(self.query(mask=mask)["selected"], self.frames[0]["slots"]["subject"])

    def test_contiguous_partial_recovery(self):
        mask = np.arange(2048) < 512
        self.assertEqual(self.query(mask=mask)["selected"], self.frames[0]["slots"]["subject"])

    def test_masked_values_cannot_affect_decoding(self):
        mask = np.arange(2048) < 512
        changed = self.samples.copy()
        changed[~mask] = 10000 + 10000j
        self.assertEqual(self.query(mask=mask), self.query(changed, mask=mask))

    def test_zero_mask_abstains(self):
        self.assertEqual(self.query(mask=np.zeros(2048, bool))["reason"], "insufficient_observed_components")

    def test_too_few_components_abstains(self):
        self.assertIsNone(self.query(mask=np.arange(2048) < 63)["selected"])

    def test_empty_signal_abstains(self):
        self.assertIsNone(self.query(np.zeros(2048, complex))["selected"])

    def test_absent_event_abstains_in_control_case(self):
        result = decode(self.samples, self.book, "synthetic:doc", "not-present", "subject", self.candidates)
        self.assertIsNone(result["selected"])

    def test_candidate_missing_abstains_in_control_case(self):
        frame = self.frames[0]
        result = decode(self.samples, self.book, frame["document_id"], frame["event_id"], "subject", self.candidates[1:])
        self.assertIsNone(result["selected"])

    def test_ambiguous_superposition_abstains(self):
        key = self.book.key("synthetic:doc", "event-000", "subject")
        ambiguous = key * (self.book.value(self.candidates[0]) + self.book.value(self.candidates[1]))
        self.assertEqual(self.query(ambiguous)["reason"], "ambiguous_candidates")

    def test_quarter_turn_requires_phase_reference(self):
        self.assertIsNone(self.query(self.samples * 1j)["selected"])

    def test_known_phase_inverse_is_not_automatic_synchronization(self):
        offset = .7
        corrected = self.samples * np.exp(1j * offset) * np.exp(-1j * offset)
        self.assertEqual(self.query(corrected)["selected"], self.frames[0]["slots"]["subject"])

    def test_channel_seed_reproducible(self):
        a, ma = channel(self.samples, seed=41, keep_fraction=.25, noise_std=.2)
        b, mb = channel(self.samples, seed=41, keep_fraction=.25, noise_std=.2)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(ma, mb)
        self.assertTrue(np.all(a[~ma] == 0))

    def test_low_noise_recovery(self):
        signal, mask = channel(self.samples, seed=52, keep_fraction=.5, noise_std=.1)
        self.assertEqual(self.query(signal, mask=mask)["selected"], self.frames[0]["slots"]["subject"])

    def test_negative_is_not_numerical_sign_flip(self):
        positive = self.book.value(symbol("state", "polarity:positive"))
        negative = self.book.value(symbol("state", "polarity:negative"))
        self.assertFalse(np.allclose(negative, -positive))

    def test_scores_are_not_probabilities(self):
        result = self.query(self.samples * 2)
        self.assertGreater(result["top_candidates"][0]["score"], 1)
        self.assertIn("not_probability", result["score_kind"])

    def test_empty_frames_encode_zero(self):
        self.assertTrue(np.all(encode([], self.book) == 0))

    def test_empty_dictionary_abstains(self):
        result = decode(self.samples, self.book, "synthetic:doc", "event-000", "subject", [])
        self.assertEqual(result["reason"], "empty_candidate_dictionary")

    def test_role_and_event_ablations(self):
        result = structural_ablations()
        self.assertTrue(all(value for value in result.values() if isinstance(value, bool)))

    def test_default_policy_matches_protocol(self):
        self.assertEqual(DecodePolicy(), DecodePolicy(**PROTOCOL["policy"]))

    def test_seed_partitions_disjoint(self):
        self.assertFalse(set(PROTOCOL["development_seeds"]) & set(PROTOCOL["evaluation_seeds"]))

    def test_reproducible_across_python_hash_seed(self):
        code = "from plm_p1 import PhaseCodebook,symbol; import hashlib; print(hashlib.sha256(PhaseCodebook().value(symbol('entity','A','doc')).tobytes()).hexdigest())"
        output = []
        for seed in ("1", "987"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            output.append(subprocess.check_output([sys.executable, "-B", "-c", code], env=env, text=True).strip())
        self.assertEqual(*output)


def invalid_test(action):
    def test(self):
        with self.assertRaises((ValueError, TypeError)):
            action(self)
    return test


INVALID = {
    "dimension_bool": lambda t: PhaseCodebook(True),
    "dimension_small": lambda t: PhaseCodebook(64),
    "dimension_nonmultiple": lambda t: PhaseCodebook(129),
    "dimension_huge": lambda t: PhaseCodebook(1000000000),
    "blank_seed": lambda t: PhaseCodebook(seed=" "),
    "namespace": lambda t: t.book.code("unknown", "x"),
    "duplicate_event": lambda t: encode([t.frames[0], t.frames[0]], t.book),
    "bad_scope": lambda t: encode([dict(t.frames[0], document_id="other")], t.book),
    "inference": lambda t: encode([dict(t.frames[0], metadata={"eligible_for_inference": True})], t.book),
    "unknown_role": lambda t: decode(t.samples, t.book, "doc", "event", "invented", t.candidates),
    "duplicate_candidate": lambda t: decode(t.samples, t.book, "doc", "event", "subject", [t.candidates[0], t.candidates[0]]),
    "signal_shape": lambda t: t.query(np.zeros((2048, 1))),
    "signal_nan": lambda t: t.query(np.full(2048, np.nan)),
    "signal_infinite": lambda t: t.query(np.full(2048, np.inf)),
    "integer_mask": lambda t: t.query(mask=np.ones(2048, dtype=int)),
    "mask_shape": lambda t: t.query(mask=np.ones(10, dtype=bool)),
    "negative_threshold": lambda t: t.query(policy=DecodePolicy(min_score=-1)),
    "zero_margin": lambda t: t.query(policy=DecodePolicy(min_margin=0)),
    "channel_range": lambda t: channel(t.samples, seed=1, keep_fraction=1.1),
    "negative_noise": lambda t: channel(t.samples, seed=1, noise_std=-1),
    "nonfinite_phase": lambda t: channel(t.samples, seed=1, phase_offset=float("nan")),
}
for name, action in INVALID.items():
    setattr(CoreTests, "test_reject_" + name, invalid_test(action))


if __name__ == "__main__":
    unittest.main()
