import unittest
from dataclasses import replace
import numpy as np
import plm_s1
from plm_p1.core import PhaseCodebook,encode
from plm_p1_v02.fixtures import make_frames
from plm_s1.link import Link,spreading_codes,pilots,spread,transmit,shifted,simulate_channel,despread_aligned
from plm_s1.receiver import synchronize


class LinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book=PhaseCodebook(2048,"s1-unit-book")
        cls.link=Link()
        cls.values=encode(make_frames(4),cls.book)
        cls.frame,cls.norm=transmit(cls.values,cls.book,cls.link)

    def test_frame_budget(self):
        self.assertEqual(self.link.frame_length,8480)
        self.assertEqual(self.link.payload_length,8192)
        self.assertEqual(self.link.tail_start-self.link.guard_length,8320)
        self.assertAlmostEqual(np.vdot(self.frame,self.frame).real,57344.,places=7)

    def test_guard_is_explicit_and_zero(self):
        self.assertTrue(np.all(self.frame[:16]==0))
        self.assertTrue(np.all(self.frame[-16:]==0))

    def test_chip_sequence_not_just_symbol_vector(self):
        chips=spread(self.values,self.book,self.link)
        self.assertEqual(chips.shape,(8192,))
        self.assertEqual(set(np.unique(spreading_codes(self.book,self.link))),{-1.,1.})

    def test_balanced_codes(self):
        codes=spreading_codes(self.book,self.link)
        np.testing.assert_array_equal(codes.sum(axis=1),np.zeros(2048))

    def test_code_deterministic_and_seed_sensitive(self):
        a=spreading_codes(self.book,self.link)
        np.testing.assert_array_equal(a,spreading_codes(self.book,self.link))
        self.assertFalse(np.array_equal(a,spreading_codes(self.book,replace(self.link,spreading_seed="other"))))

    def test_returned_codes_are_not_shared_mutable_state(self):
        a=spreading_codes(self.book,self.link)
        a[:]=9
        self.assertTrue(np.max(spreading_codes(self.book,self.link))<=1)

    def test_pilot_blocks_are_distinct(self):
        head,tail=pilots(self.book,self.link)
        self.assertFalse(np.array_equal(head,tail))

    def test_spread_energy_preserved(self):
        chips=spread(self.values,self.book,self.link)
        self.assertAlmostEqual(np.vdot(chips,chips).real,np.vdot(self.values,self.values).real,places=7)

    def test_equal_all_mode_energy_and_time(self):
        for mode in ("spread","repeat","direct_sparse"):
            link=replace(self.link,mode=mode)
            y,norm=transmit(self.values,self.book,link)
            self.assertEqual(len(y),8480)
            self.assertAlmostEqual(np.vdot(y,y).real,57344.,places=7)
            self.assertEqual(norm["pilot_amplitude"],self.norm["pilot_amplitude"])

    def test_all_modes_exact_noiseless_roundtrip(self):
        for mode in ("spread","repeat","direct_sparse"):
            link=replace(self.link,mode=mode)
            tx,norm=transmit(self.values,self.book,link)
            result,mask,_=despread_aligned(tx,None,self.book,link,norm)
            np.testing.assert_allclose(result,self.values,rtol=1e-12,atol=1e-12)
            self.assertTrue(mask.all())

    def test_one_chip_per_component_is_sufficient_without_noise(self):
        mask=np.zeros(8480,bool)
        mask[self.link.payload_start:self.link.tail_start:4]=True
        result,observed,info=despread_aligned(self.frame,mask,self.book,self.link,self.norm)
        self.assertTrue(observed.all())
        np.testing.assert_allclose(result,self.values,rtol=1e-12,atol=1e-12)
        self.assertEqual(info["observed_data_bearing_chips"],2048)

    def test_zero_observation_stays_missing(self):
        y,m,info=despread_aligned(self.frame,np.zeros(8480,bool),self.book,self.link,self.norm)
        self.assertFalse(m.any())
        self.assertTrue(np.all(y==0))

    def test_observed_zero_is_not_missing(self):
        y,m,_=despread_aligned(np.zeros(8480),None,self.book,self.link,self.norm)
        self.assertTrue(m.all())
        self.assertTrue(np.all(y==0))

    def test_partial_mask_does_not_read_hidden_chips(self):
        mask=np.arange(8480)%3==0
        changed=self.frame.copy()
        changed[~mask]=1e8+9j
        a=despread_aligned(self.frame,mask,self.book,self.link,self.norm)
        b=despread_aligned(changed,mask,self.book,self.link,self.norm)
        np.testing.assert_array_equal(a[0],b[0])

    def test_mismatched_spreading_code_destroys_roundtrip(self):
        y,m,_=despread_aligned(self.frame,None,self.book,replace(self.link,spreading_seed="wrong"),self.norm)
        self.assertGreater(float(np.mean(abs(y-self.values)**2)),1.)

    def test_dc_interference_cancels_for_full_balanced_chips(self):
        y,m,_=despread_aligned(self.frame+3+2j,None,self.book,self.link,self.norm)
        np.testing.assert_allclose(y,self.values,rtol=1e-12,atol=1e-12)

    def test_repeat_does_not_cancel_dc(self):
        link=replace(self.link,mode="repeat")
        frame,norm=transmit(self.values,self.book,link)
        y,_,_=despread_aligned(frame+3+2j,None,self.book,link,norm)
        self.assertGreater(float(np.mean(abs(y-self.values)**2)),1.)

    def test_masks_and_channel_are_deterministic(self):
        a=simulate_channel(self.frame,self.link,seed=33,keep_fraction=.25,noise_std=.25)
        b=simulate_channel(self.frame,self.link,seed=33,keep_fraction=.25,noise_std=.25)
        np.testing.assert_array_equal(a[0],b[0])
        np.testing.assert_array_equal(a[1],b[1])
        self.assertEqual(int(a[1].sum()),2120)

    def test_channel_does_not_mutate_transmitter(self):
        before=self.frame.copy()
        simulate_channel(self.frame,self.link,seed=4,delay_chips=8,cfo_hz=.1,phase_rad=1.2)
        np.testing.assert_array_equal(before,self.frame)

    def test_shift_handles_both_signs_without_wraparound(self):
        np.testing.assert_array_equal(shifted(np.arange(5),2),[0,0,0,1,2])
        np.testing.assert_array_equal(shifted(np.arange(5),-2),[2,3,4,0,0])

    def test_empty_payload_rejected(self):
        with self.assertRaises(ValueError): transmit(np.zeros(2048),self.book,self.link)

    def test_dimension_mismatch_rejected(self):
        with self.assertRaises(ValueError): spreading_codes(PhaseCodebook(512,"wrong"),self.link)


def parameter_test(field,value):
    def test(self):
        with self.assertRaises((ValueError,TypeError)): replace(self.link,**{field:value}).validate()
    return test


for i,(field,value) in enumerate([("dimension",True),("dimension",127),("dimension",8192),("chips_per_component",1),("chips_per_component",3),("pilot_length",8),("guard_length",-1),("max_delay_chips",17),("max_delay_chips",True),("chip_rate_hz",0),("chip_rate_hz",float("inf")),("max_abs_cfo_hz",1.),("max_abs_cfo_hz",0),("spreading_seed",""),("mode","unknown")]):
    setattr(LinkTests,f"test_invalid_link_{i:02d}",parameter_test(field,value))


if __name__=="__main__": unittest.main()
