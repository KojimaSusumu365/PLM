import unittest
from copy import deepcopy
from dataclasses import replace
import numpy as np
import plm_s1
from plm_p1.core import PhaseCodebook,encode,digest
from plm_p1_v02.fixtures import make_frames,public_catalogue,entity_candidates,DOC
from plm_s1.link import Link,transmit,simulate_channel,despread_aligned
from plm_s1.packet import to_packet,from_packet
from plm_s1.receiver import synchronize,Session


class SyncPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book=PhaseCodebook(2048,"s1-sync-tests")
        cls.link=Link()
        cls.frames=make_frames(4)
        cls.memory=encode(cls.frames,cls.book)
        cls.frame,cls.norm=transmit(cls.memory,cls.book,cls.link)
        y,m=simulate_channel(cls.frame,cls.link,seed=78,delay_chips=-5,phase_rad=1.7,cfo_hz=.13,keep_fraction=.25,noise_std=.25,jitter_std=.03)
        cls.packet=to_packet(y,m,cls.book,cls.link,cls.norm,source_digest=digest(cls.frames))
        cls.query={"document_id":DOC,"event_id":"event-000","role":"subject","candidates":entity_candidates()}

    def session(self,packet=None):
        return Session(packet or self.packet,public_catalogue(),expected_book=self.book,expected_link=self.link)

    def test_integer_delay_and_frequency_estimated(self):
        s=self.session()
        r=s.synchronization
        self.assertEqual(r["status"],"aligned")
        self.assertEqual(r["estimated_delay_chips"],-5)
        self.assertLess(abs(r["estimated_cfo_hz"]-.13),.015)
        self.assertLess(abs(r["estimated_phase_rad"]-1.7),.07)

    def test_partial_link_all_entity_slots(self):
        s=self.session()
        for f in self.frames:
            for role in ("subject","object"):
                r=s.query(dict(self.query,event_id=f["event_id"],role=role))
                self.assertEqual(r["selected"],f["slots"][role])
                self.assertIs(r["eligible_for_inference"],False)

    def test_absent_event_abstains(self):
        self.assertIsNone(self.session().query(dict(self.query,event_id="absent-event-000"))["selected"])

    def test_missing_true_candidate_abstains(self):
        self.assertIsNone(self.session().query(dict(self.query,candidates=entity_candidates()[1:]))["selected"])

    def test_frame_and_time_axis_roundtrip(self):
        y,m,b,l,n=from_packet(self.packet,expected_book=self.book,expected_link=self.link)
        self.assertEqual(to_packet(y,m,b,l,n,source_digest=digest(self.frames)),self.packet)
        self.assertEqual(self.packet["time_axis"]["sample_spacing_seconds"],1/8000)

    def test_missing_pilots_abstains_even_with_known_catalogue(self):
        y,m=simulate_channel(self.frame,self.link,seed=2,erase_pilots=True)
        p=to_packet(y,m,self.book,self.link,self.norm,source_digest=digest(self.frames))
        s=self.session(p)
        self.assertEqual(s.synchronization["status"],"abstain")
        self.assertIsNone(s.query(self.query)["selected"])

    def test_no_chips_abstains(self):
        p=to_packet(self.frame,np.zeros(8480,bool),self.book,self.link,self.norm,source_digest=digest(self.frames))
        self.assertIsNone(self.session(p).query(self.query)["selected"])

    def test_wrong_pilot_pattern_abstains(self):
        y=self.frame.copy()
        rng=np.random.default_rng(111)
        for start in (16,self.link.tail_start): y[start:start+128]*=rng.choice([-1,1],128)
        p=to_packet(y,None,self.book,self.link,self.norm,source_digest=digest(self.frames))
        self.assertEqual(self.session(p).synchronization["status"],"abstain")

    def test_outside_delay_search_abstains(self):
        y,m=simulate_channel(self.frame,self.link,seed=4,delay_chips=11)
        p=to_packet(y,m,self.book,self.link,self.norm,source_digest=digest(self.frames))
        self.assertEqual(self.session(p).synchronization["status"],"abstain")

    def test_query_gold_rejected(self):
        with self.assertRaises(ValueError): self.session().query(dict(self.query,gold=self.frames[0]["slots"]["subject"]))

    def test_query_bad_role_rejected_even_when_sync_fails(self):
        p=to_packet(self.frame,np.zeros(8480,bool),self.book,self.link,self.norm,source_digest=digest(self.frames))
        with self.assertRaises(ValueError): self.session(p).query(dict(self.query,role="unknown"))

    def test_result_diagnostics_not_shared(self):
        s=self.session()
        r=s.query(self.query)
        r["synchronization"]["status"]="tampered"
        self.assertEqual(s.synchronization["status"],"aligned")

    def test_pinned_spreading_config_mismatch(self):
        with self.assertRaises(ValueError): from_packet(self.packet,expected_link=replace(self.link,spreading_seed="wrong"))

    def test_pinned_book_mismatch(self):
        with self.assertRaises(ValueError): from_packet(self.packet,expected_book=PhaseCodebook(2048,"wrong"))

    def test_actual_receiver_requires_book_pin(self):
        with self.assertRaises(ValueError): Session(self.packet,public_catalogue(),expected_book=None,expected_link=self.link)

    def test_actual_receiver_requires_link_pin(self):
        with self.assertRaises(ValueError): Session(self.packet,public_catalogue(),expected_book=self.book,expected_link=None)

    def test_source_digest_is_not_a_truth_lookup(self):
        p=deepcopy(self.packet)
        p["source_digest"]="0"*64
        p["payload_hash"]=digest({k:v for k,v in p.items() if k!="payload_hash"})
        self.assertEqual(self.session().query(self.query),self.session(p).query(self.query))

    def test_ss_is_numeric_only_not_inference(self):
        self.assertIs(self.packet["boundary"]["ss_demodulation_implemented"],True)
        self.assertIs(self.packet["boundary"]["inference_enabled"],False)
        self.assertEqual(self.packet["boundary"]["implementation_scope"],"synthetic_discrete_complex_baseband_only")


def mutate_packet(fn,rehash=True):
    def test(self):
        p=deepcopy(self.packet)
        fn(p)
        if rehash: p["payload_hash"]=digest({k:v for k,v in p.items() if k!="payload_hash"})
        with self.assertRaises((ValueError,TypeError)): from_packet(p)
    return test


for i,fn in enumerate([
    lambda p:p.update(gold={}),lambda p:p.update(delay_chips=-5),lambda p:p.update(cfo_hz=.13),lambda p:p.update(phase_rad=1.7),
    lambda p:p["normalization"].update(true_phase=1.7),lambda p:p["normalization"].update(payload_gain=0),
    lambda p:p["normalization"].update(pilot_amplitude=7),lambda p:p["boundary"].update(inference_enabled=True),
    lambda p:p["boundary"].update(inference_enabled=0),lambda p:p["boundary"].update(ss_demodulation_implemented=1),
    lambda p:p["time_axis"].update(sample_count=8481),lambda p:p["time_axis"].update(origin_seconds=True),
    lambda p:p["observed_mask"].__setitem__(0,1),lambda p:p["samples"]["real"].pop(),
    lambda p:p["samples"]["real"].__setitem__(next(i for i,x in enumerate(p["observed_mask"]) if not x),1),
    lambda p:p["link"].update(mode="unknown"),lambda p:p["link"].update(actual_delay=5),
    lambda p:p["codebook"].update(seed="wrong"),lambda p:p.update(source_digest="wrong")
]): setattr(SyncPacketTests,f"test_invalid_packet_{i:02d}",mutate_packet(fn))
setattr(SyncPacketTests,"test_checksum_corruption",mutate_packet(lambda p:p["normalization"].update(payload_gain=2),False))


def exact_offsets(delay,phi,cfo):
    def test(self):
        y,m=simulate_channel(self.frame,self.link,seed=41,delay_chips=delay,phase_rad=phi,cfo_hz=cfo)
        aligned,mask,r=synchronize(y,m,self.book,self.link,self.norm)
        self.assertEqual(r["status"],"aligned")
        self.assertEqual(r["estimated_delay_chips"],delay)
        self.assertLess(abs(r["estimated_cfo_hz"]-cfo),1e-8)
        recovered,obs,_=despread_aligned(aligned,mask,self.book,self.link,self.norm)
        np.testing.assert_allclose(recovered,self.memory,rtol=1e-10,atol=1e-10)
    return test


for i,settings in enumerate([(0,0.,0.),(-8,2.7,0.),(8,-2.9,0.),(0,0.,.15),(0,0.,-.15),(-3,-2.5,.17),(7,1.2,-.17)]):
    setattr(SyncPacketTests,f"test_exact_offsets_{i:02d}",exact_offsets(*settings))


if __name__=="__main__": unittest.main()
