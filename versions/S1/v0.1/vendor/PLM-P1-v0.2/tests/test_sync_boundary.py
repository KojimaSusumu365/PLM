import unittest
from copy import deepcopy
import numpy as np
import plm_p1_v02
from plm_p1.core import PhaseCodebook, encode, channel, digest
from plm_p1.packet import to_packet, from_packet
from plm_p1_v02.sync import pilot_frame,to_pilot_packet,from_pilot_packet,synchronize
from plm_p1_v02.fixtures import make_frames,public_catalogue,entity_candidates,DOC
from plm_p1_v02.recovery import Receiver


class SyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book=PhaseCodebook(2048,"pilot-unit-v02")
        cls.frames=make_frames(4)
        cls.memory=encode(cls.frames,cls.book)
        cls.tx,cls.config=pilot_frame(cls.memory,cls.book)
        y,mask=channel(cls.tx,seed=666,keep_fraction=.25,noise_std=.15,phase_offset=1.3,jitter_std=.1)
        cls.packet=to_pilot_packet(y,mask,cls.book,cls.config)

    def test_fixed_total_dimension_and_energy(self):
        self.assertEqual(len(self.tx),2048)
        self.assertAlmostEqual(float(np.vdot(self.tx,self.tx).real),2048*28,places=7)

    def test_pilots_consume_payload_coordinates(self):
        values,mask,book,r=synchronize(self.packet)
        self.assertFalse(mask[-128:].any())
        self.assertTrue(np.all(values[-128:]==0))
        self.assertLess(mask.sum(),512)

    def test_phase_estimated_without_oracle(self):
        values,mask,book,r=synchronize(self.packet)
        self.assertEqual(r["status"],"aligned")
        self.assertLess(abs(r["estimated_phase_rad"]-1.3),.08)
        self.assertEqual(set(self.packet["pilot"]),{"length","sequence","amplitude","payload_gain"})

    def test_synchronized_recovery(self):
        values,mask,book,r=synchronize(self.packet)
        receiver=Receiver(values,mask,book,public_catalogue())
        for f in self.frames:
            for role in ("subject","object"):
                result=receiver.scores(DOC,f["event_id"],role,entity_candidates())
                self.assertEqual(result["selected"],f["slots"][role])
                self.assertIs(result["eligible_for_inference"],False)

    def test_no_pilot_abstains(self):
        y,m,b,p=from_pilot_packet(self.packet)
        m[-128:]=False
        no=to_pilot_packet(y,m,b,p)
        values,mask,book,r=synchronize(no)
        self.assertEqual(r["status"],"abstain")
        self.assertTrue(np.all(values==0))

    def test_zero_pilot_abstains(self):
        y,m,b,p=from_pilot_packet(self.packet)
        y[-128:]=0
        no=to_pilot_packet(y,m,b,p)
        self.assertEqual(synchronize(no)[3]["reason"],"pilot_coherence_too_low")

    def test_wrong_pilot_abstains(self):
        y,m,b,p=from_pilot_packet(self.packet)
        rng=np.random.default_rng(77)
        y[-128:]=np.exp(1j*rng.uniform(-np.pi,np.pi,128))
        no=to_pilot_packet(y,m,b,p)
        self.assertEqual(synchronize(no)[3]["status"],"abstain")

    def test_bad_pinned_book(self):
        with self.assertRaises(ValueError): synchronize(self.packet,expected_book=PhaseCodebook(2048,"wrong"))

    def test_legacy_wire_still_exact(self):
        packet=to_packet(self.memory,None,self.book)
        y,m,b=from_packet(packet,expected_codebook=self.book)
        self.assertTrue(np.array_equal(y,self.memory))

    def test_no_ss_or_truth_claim(self):
        self.assertIs(self.packet["boundary"]["ss_demodulation_implemented"],False)
        self.assertIsNone(self.packet["chip_rate_hz"])

    def test_packet_roundtrip(self):
        y,m,b,p=from_pilot_packet(self.packet)
        self.assertEqual(to_pilot_packet(y,m,b,p),self.packet)

    def test_input_not_mutated(self):
        original=self.memory.copy()
        pilot_frame(self.memory,self.book)
        np.testing.assert_array_equal(original,self.memory)

    def test_invalid_empty_payload(self):
        with self.assertRaises(ValueError): pilot_frame(np.zeros(2048),self.book)


def rejection(mutate,rehash=True):
    def test(self):
        packet=deepcopy(self.packet)
        mutate(packet)
        if rehash: packet["payload_hash"]=digest({k:v for k,v in packet.items() if k!="payload_hash"})
        with self.assertRaises((ValueError,TypeError)): from_pilot_packet(packet)
    return test


for i,fn in enumerate([
    lambda p:p.update(gold={}),lambda p:p.update(phase_offset=1.3),lambda p:p.update(format="old"),
    lambda p:p["pilot"].update(true_phase=1.3),lambda p:p["pilot"].update(length=True),
    lambda p:p["pilot"].update(length=2048),lambda p:p["pilot"].update(payload_gain=0),
    lambda p:p["pilot"].update(amplitude=-1),lambda p:p["pilot"].update(sequence="private"),
    lambda p:p["boundary"].update(inference_enabled=True),lambda p:p["boundary"].update(inference_enabled=0),
    lambda p:p["boundary"].update(ss_demodulation_implemented=True),lambda p:p.update(chip_rate_hz=1000),
    lambda p:p["samples"]["real"].pop(),lambda p:p["observed_mask"].__setitem__(0,1),
    lambda p:p["codebook"].update(seed="different"),
    lambda p:p["samples"]["real"].__setitem__(next(i for i,x in enumerate(p["observed_mask"]) if not x),1),
]):
    setattr(SyncTests,f"test_invalid_packet_{i:02d}",rejection(fn))
setattr(SyncTests,"test_corruption_hash",rejection(lambda p:p["pilot"].update(amplitude=3),False))


if __name__ == "__main__": unittest.main()
