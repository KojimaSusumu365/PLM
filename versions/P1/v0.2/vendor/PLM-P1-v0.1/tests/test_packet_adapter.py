from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from plm_p1 import PhaseCodebook, encode, decode, to_packet, from_packet
from plm_p1.core import channel, digest
from plm_p1.fixtures import make_frames, entity_candidates
from plm_p1.adapter import source_refs, verify_dependency, r1_module, from_r1_envelope
from plm_p1.__main__ import load_json


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.book = PhaseCodebook(2048, "packet-tests")
        self.frames = make_frames(2)
        self.signal, self.mask = channel(encode(self.frames, self.book), seed=125, keep_fraction=.5, noise_std=.1)
        self.packet = to_packet(self.signal, self.mask, self.book, source_refs=source_refs(self.frames))

    def test_json_roundtrip_exact(self):
        packet = json.loads(json.dumps(self.packet, ensure_ascii=False))
        values, mask, book = from_packet(packet, expected_codebook=self.book)
        np.testing.assert_array_equal(values, self.signal)
        np.testing.assert_array_equal(mask, self.mask)
        self.assertEqual(book.spec, self.book.spec)

    def test_missing_samples_zeroed_on_export(self):
        packet = to_packet(encode(self.frames, self.book), self.mask, self.book)
        values, mask, _ = from_packet(packet)
        self.assertTrue(np.all(values[~mask] == 0))

    def test_no_ground_truth_in_packet(self):
        encoded = json.dumps(self.packet)
        self.assertNotIn('"slots"', encoded)
        self.assertNotIn('"metadata"', encoded)
        self.assertNotIn('"animal-000"', encoded)

    def test_decode_without_source_references(self):
        packet = deepcopy(self.packet)
        packet["source_refs"] = []
        packet["payload_hash"] = digest({k: v for k, v in packet.items() if k != "payload_hash"})
        values, mask, book = from_packet(packet)
        frame = self.frames[0]
        result = decode(values, book, frame["document_id"], frame["event_id"], "subject", entity_candidates(), mask=mask)
        self.assertEqual(result["selected"], frame["slots"]["subject"])

    def test_packet_export_is_independent_copy(self):
        old = self.packet["samples"]["real"][0]
        self.signal[0] = 900
        self.assertEqual(self.packet["samples"]["real"][0], old)

    def test_wrong_receiver_codebook_rejected(self):
        with self.assertRaises(ValueError):
            from_packet(self.packet, expected_codebook=PhaseCodebook(2048, "wrong"))

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.json"
            path.write_text('{"key":1,"key":2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json(path)

    def test_nonfinite_json_number_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.json"
            path.write_text('{"key":NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json(path)


def packet_mutation(action, rehash=True):
    def test(self):
        value = deepcopy(self.packet)
        action(value)
        if rehash:
            value["payload_hash"] = digest({k: v for k, v in value.items() if k != "payload_hash"})
        with self.assertRaises((ValueError, TypeError, KeyError)):
            from_packet(value)
    return test


MUTATIONS = {
    "corrupted_hash": (lambda p: p.update(payload_hash="wrong"), False),
    "tampered_signal": (lambda p: p["samples"]["real"].__setitem__(0, 100), False),
    "version": (lambda p: p.update(format="unknown"), True),
    "codec": (lambda p: p.update(codec="unbound-bag"), True),
    "slot_leak": (lambda p: p.update(slots={"subject": "animal-000"}), True),
    "false_inference": (lambda p: p["boundary"].update(inference_enabled=True), True),
    "numeric_false_flag": (lambda p: p["boundary"].update(inference_enabled=0), True),
    "claim_ss_complete": (lambda p: p["boundary"].update(ss_demodulation_implemented=True), True),
    "claimed_independent": (lambda p: p["boundary"].update(independent_semantic_validation="passed"), True),
    "dimension": (lambda p: p["codebook"].update(dimension=128), True),
    "algorithm": (lambda p: p["codebook"].update(algorithm="random-hash"), True),
    "phase_units": (lambda p: p["codebook"].update(phase_units="degrees"), True),
    "fingerprint": (lambda p: p.update(codebook_fingerprint="wrong"), True),
    "short_signal": (lambda p: p["samples"]["imag"].pop(), True),
    "boolean_signal": (lambda p: p["samples"]["real"].__setitem__(0, True), True),
    "numeric_mask": (lambda p: p["observed_mask"].__setitem__(0, 1), True),
    "wrong_amplitude_scale": (lambda p: p.update(normalization="unit_norm"), True),
    "unknown_phase_reference": (lambda p: p.update(phase_reference="automatically_synchronized"), True),
    "invented_chip_rate": (lambda p: p.update(chip_rate_hz=1000), True),
    "source_slot_leak": (lambda p: p["source_refs"][0].update(slots={"subject":"animal-000"}), True),
    "duplicate_source": (lambda p: p["source_refs"].append(deepcopy(p["source_refs"][0])), True),
    "invalid_source_hash": (lambda p: p["source_refs"][0].update(source_record_hash="not_a_hash"), True),
    "masked_signal_leak": (lambda p: p["samples"]["real"].__setitem__(p["observed_mask"].index(False), 1.0), True),
}
for name, (action, rehash) in MUTATIONS.items():
    setattr(PacketTests, "test_reject_" + name, packet_mutation(action, rehash))


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r1 = r1_module()

    def envelope(self, text):
        return self.r1.export_observations(self.r1.analyze(text))

    def test_frozen_r1_inventory(self):
        self.assertEqual(verify_dependency()["inventory_files"], 117)

    def test_negative_preserved(self):
        frames = from_r1_envelope(self.envelope("The bank did not grant aid."))
        self.assertEqual(frames[0]["slots"]["polarity"]["id"], "polarity:negative")
        self.assertFalse(frames[0]["metadata"]["eligible_for_inference"])

    def test_hypothetical_preserved(self):
        frames = from_r1_envelope(self.envelope("If the bank grants aid."))
        self.assertEqual(frames[0]["slots"]["modality"]["id"], "modality:hypothetical")

    def test_quarantine_preserved(self):
        frames = from_r1_envelope(self.envelope('"The bank granted aid."'))
        self.assertTrue(frames)
        self.assertTrue(all(f["slots"]["semantic_status"]["id"] == "semantic_status:quarantined" for f in frames))

    def test_revision_target_and_missing_entities(self):
        frames = from_r1_envelope(self.envelope("Originally marked dog: reclassified as cat."))
        self.assertEqual(frames[0]["slots"]["target_clause"]["id"], "S001:C001")
        self.assertNotIn("subject", frames[0]["slots"])
        self.assertNotIn("object", frames[0]["slots"])

    def test_original_observation_preserved(self):
        envelope = self.envelope("The bank granted aid.")
        frames = from_r1_envelope(envelope)
        self.assertEqual(frames[0]["metadata"]["source_observation"], envelope["observations"][0])
        envelope["observations"][0]["predicate"] = "changed"
        self.assertNotEqual(frames[0]["metadata"]["source_observation"]["predicate"], "changed")

    def test_same_concept_distinct_entities(self):
        frames = from_r1_envelope(self.envelope(["A dog and another dog entered.", "They were photographed."]))
        self.assertEqual(len({f["slots"]["object"]["id"] for f in frames}), 2)

    def test_r1_states_numerical_recovery(self):
        frames = from_r1_envelope(self.envelope("The bank did not grant aid."))
        book = PhaseCodebook()
        for role in ("polarity", "modality", "semantic_status"):
            result = decode(encode(frames, book), book, frames[0]["document_id"], frames[0]["event_id"], role, [frames[0]["slots"][role]])
            self.assertEqual(result["selected"], frames[0]["slots"][role])
            self.assertFalse(result["eligible_for_inference"])

    def test_empty_observations_do_not_invent_frames(self):
        self.assertEqual(from_r1_envelope(self.envelope([])), [])

    def test_invalid_r1_boundary_rejected(self):
        envelope = self.envelope("The bank granted aid.")
        envelope["boundary"]["inference_enabled"] = True
        with self.assertRaises(ValueError):
            from_r1_envelope(envelope)


if __name__ == "__main__":
    unittest.main()
