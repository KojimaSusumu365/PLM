import copy
from dataclasses import replace
import unittest
import numpy as np
import plm_s1_v02
from plm_p1.core import PhaseCodebook,encode,digest
from plm_p1_v02.fixtures import make_frames,public_catalogue,entity_candidates,DOC
from plm_s1.link import Link as OldLink,transmit as old_transmit,spreading_codes
from plm_s1.receiver import synchronize as old_sync
from plm_s1_v02.link import Link,transmit,simulate_channel,despread_aligned,pilots,shifted
from plm_s1_v02.packet import to_packet,from_packet
from plm_s1_v02.receiver import Session,synchronize

BOOK=PhaseCodebook(2048,'s1-v02-code-53101')
FRAMES=make_frames(4)
MEMORY=encode(FRAMES,BOOK)
CAT=public_catalogue()
LINK=Link()
TX,NORM=transmit(MEMORY,BOOK,LINK)


def packet(y=TX,m=None,book=BOOK,link=LINK,norm=NORM):
    return to_packet(y,m,book,link,norm,source_digest=digest(FRAMES))


def perturbed(**kwargs):
    params=dict(seed=62101,phase_rad=1.8,cfo_hz=1.061538,delay_chips=-5,keep_fraction=.25,noise_std=.25,jitter_std=.03)
    params.update(kwargs)
    return simulate_channel(TX,LINK,**params)


def query():
    return dict(document_id=DOC,event_id=FRAMES[0]['event_id'],role='subject',candidates=entity_candidates())


class FramingTests(unittest.TestCase):
    def test_layout_lengths(self):
        self.assertEqual(LINK.pilot_starts,(16,3000,4700,8400))
        self.assertEqual(len(LINK.data_indices),8192)
        self.assertEqual(sum(map(len,LINK.pilot_indices)),256)
        self.assertEqual(len(TX),8480)

    def test_disjoint_complete_layout(self):
        all_ix=np.concatenate([LINK.data_indices,*LINK.pilot_indices,np.arange(16),np.arange(8464,8480)])
        np.testing.assert_array_equal(np.sort(all_ix),np.arange(8480))

    def test_energy_and_guard(self):
        self.assertAlmostEqual(float(np.vdot(TX,TX).real),57344.,places=7)
        self.assertTrue(np.all(TX[:16]==0) and np.all(TX[-16:]==0))
        self.assertAlmostEqual(NORM['pilot_amplitude']**2*256,1737.6969696969697)

    def test_all_mode_budgets(self):
        for mode in ('spread','repeat','direct_sparse'):
            link=replace(LINK,mode=mode)
            tx,norm=transmit(MEMORY,BOOK,link)
            self.assertEqual(len(tx),8480)
            self.assertAlmostEqual(float(np.vdot(tx,tx).real),57344.,places=7)
            values,mask,_=despread_aligned(tx,None,BOOK,link,norm)
            np.testing.assert_allclose(values,MEMORY,atol=1e-13)
            self.assertTrue(mask.all())

    def test_edge_layout_exact_legacy_waveform(self):
        tx,norm=transmit(MEMORY,BOOK,replace(LINK,layout='edge2'))
        old,onorm=old_transmit(MEMORY,BOOK,OldLink())
        np.testing.assert_allclose(tx,old,atol=1e-13)
        self.assertEqual(norm,onorm)

    def test_payload_code_unchanged(self):
        np.testing.assert_array_equal(spreading_codes(BOOK,LINK),spreading_codes(BOOK,OldLink()))

    def test_one_chip_each(self):
        m=np.zeros(8480,bool)
        m[LINK.data_indices.reshape(2048,4)[:,2]]=True
        values,mask,info=despread_aligned(TX*m,m,BOOK,LINK,NORM)
        np.testing.assert_allclose(values,MEMORY,atol=1e-13)
        self.assertTrue(mask.all())
        self.assertEqual(info['observed_payload_chips'],2048)

    def test_zero_vs_missing(self):
        zero=np.zeros(8480,complex)
        _,present,_=despread_aligned(zero,None,BOOK,LINK,NORM)
        _,missing,_=despread_aligned(zero,np.zeros(8480,bool),BOOK,LINK,NORM)
        self.assertTrue(present.all())
        self.assertFalse(missing.any())

    def test_channel_reproducible(self):
        a,ma=perturbed()
        b,mb=perturbed()
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(ma,mb)
        self.assertTrue(np.all(a[~ma]==0))

    def test_erasure_distributed(self):
        y,m=perturbed(keep_fraction=1.,erase_pilots=True)
        for ix in LINK.pilot_indices: self.assertFalse(m[ix-5].any())
        self.assertTrue(np.all(y[~m]==0))

    def test_shift_not_circular(self):
        for delay in (-8,0,8):
            x=shifted(TX,delay)
            np.testing.assert_allclose(shifted(x,-delay),TX)

    def test_invalid_link(self):
        for key,value in [('dimension',True),('dimension',1024),('chips_per_component',8),('guard_length',0),('chip_rate_hz',float('nan')),
                          ('max_delay_chips',True),('max_delay_chips',9),('max_abs_cfo_hz',3),('acquisition_max_abs_cfo_hz',8),('layout','bad'),('mode','bad'),('spreading_seed','')]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError): replace(LINK,**{key:value}).validate()

    def test_invalid_energy(self):
        for value in (0,-1,True,float('inf')):
            with self.subTest(value=value),self.assertRaises(ValueError): transmit(MEMORY,BOOK,LINK,total_energy=value)

    def test_empty_payload_rejected(self):
        with self.assertRaises(ValueError): transmit(np.zeros(2048,complex),BOOK,LINK)


class SynchronizationTests(unittest.TestCase):
    def test_nominal_exact(self):
        y,m,s=synchronize(TX,None,BOOK,LINK,NORM)
        self.assertEqual(s['status'],'aligned')
        self.assertEqual(s['estimated_delay_chips'],0)
        self.assertEqual(s['estimated_cfo_hz'],0)
        np.testing.assert_allclose(y,TX,atol=1e-13)

    def test_noiseless_offsets(self):
        for delay in (-8,0,8):
            for f in (-1.9,-1.061538,-.480769,0,.480769,1.061538,1.9):
                with self.subTest(delay=delay,f=f):
                    y,m=perturbed(delay_chips=delay,cfo_hz=f,keep_fraction=1,noise_std=0,jitter_std=0)
                    _,_,s=synchronize(y,m,BOOK,LINK,NORM)
                    self.assertEqual(s['status'],'aligned')
                    self.assertEqual(s['estimated_delay_chips'],delay)
                    self.assertLess(abs(s['estimated_cfo_hz']-f),.00013)

    def test_partial_wide(self):
        y,m=perturbed()
        _,_,s=synchronize(y,m,BOOK,LINK,NORM)
        self.assertEqual(s['status'],'aligned')
        self.assertLess(abs(s['estimated_cfo_hz']-1.061538),.025)

    def test_old_alias_reproduced(self):
        from plm_s1.link import simulate_channel as oc
        tx,n=old_transmit(MEMORY,BOOK,OldLink())
        y,m=oc(tx,OldLink(),seed=62101,cfo_hz=8000/8320+.1,phase_rad=1.8,delay_chips=-5)
        _,_,s=old_sync(y,m,BOOK,OldLink(),n)
        self.assertEqual(s['status'],'aligned')
        self.assertGreater(abs(s['estimated_cfo_hz']-(8000/8320+.1)),.9)

    def test_edge2_ablation_ambiguous(self):
        link=replace(LINK,layout='edge2')
        tx,n=transmit(MEMORY,BOOK,link)
        _,_,s=synchronize(tx,None,BOOK,link,n)
        self.assertEqual(s['reason'],'ambiguous_frequency_candidates')

    def test_missing_one_block(self):
        m=np.ones(8480,bool)
        m[LINK.pilot_indices[1]]=False
        _,out,s=synchronize(TX*m,m,BOOK,LINK,NORM)
        self.assertEqual(s['status'],'abstain')
        self.assertFalse(out.any())

    def test_only_edges_observed(self):
        m=np.zeros(8480,bool)
        m[LINK.pilot_indices[0]]=True
        m[LINK.pilot_indices[-1]]=True
        self.assertEqual(synchronize(TX*m,m,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_zero_observation(self):
        y,m,s=synchronize(np.zeros(8480,complex),np.zeros(8480,bool),BOOK,LINK,NORM)
        self.assertEqual(s['status'],'abstain')
        self.assertFalse(m.any())

    def test_observed_zero_pilots(self):
        self.assertEqual(synchronize(np.zeros(8480,complex),None,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_noise_only(self):
        rng=np.random.default_rng(62101)
        y=rng.normal(size=8480)+1j*rng.normal(size=8480)
        self.assertEqual(synchronize(y,None,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_wrong_pilot_book(self):
        self.assertEqual(synchronize(TX,None,PhaseCodebook(2048,'wrong-pilot'),LINK,NORM)[2]['status'],'abstain')

    def test_guard_cfo_rejected(self):
        for f in (-4.5,-3,-2.05,2.05,3,4.5,8,16):
            with self.subTest(f=f):
                y,m=perturbed(cfo_hz=f)
                self.assertEqual(synchronize(y,m,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_outside_delay(self):
        y,m=perturbed(delay_chips=11,keep_fraction=1)
        self.assertEqual(synchronize(y,m,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_inconsistent_block(self):
        y=TX.copy()
        y[LINK.pilot_indices[2]]*=-1
        self.assertEqual(synchronize(y,None,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_superposed_frequencies(self):
        times=np.arange(8480)/8000
        y=TX*(np.exp(2j*np.pi*.9*times)+np.exp(-2j*np.pi*.9*times))/np.sqrt(2)
        self.assertEqual(synchronize(y,None,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_pilot_amplitude_inconsistency(self):
        y=TX.copy()
        y[LINK.pilot_indices[2]]*=3
        self.assertEqual(synchronize(y,None,BOOK,LINK,NORM)[2]['status'],'abstain')

    def test_sample_alias_is_not_detectable(self):
        # Deliberate limitation: one sample/chip cannot identify frequencies modulo Fs.
        y,m=perturbed(cfo_hz=8000.1,keep_fraction=1,noise_std=0,jitter_std=0)
        _,_,s=synchronize(y,m,BOOK,LINK,NORM)
        self.assertEqual(s['status'],'aligned')
        self.assertLess(abs(s['estimated_cfo_hz']-.1),.00013)

    def test_no_input_mutation(self):
        y,m=perturbed()
        before=y.copy(),m.copy()
        synchronize(y,m,BOOK,LINK,NORM)
        np.testing.assert_array_equal(y,before[0])
        np.testing.assert_array_equal(m,before[1])


class PacketSessionTests(unittest.TestCase):
    def bad(self,modify):
        p=packet()
        modify(p)
        p['payload_hash']=digest({k:v for k,v in p.items() if k!='payload_hash'})
        with self.assertRaises((ValueError,TypeError)): from_packet(p)

    def test_packet_roundtrip(self):
        y,m,b,l,n=from_packet(packet(),expected_book=BOOK,expected_link=LINK)
        np.testing.assert_array_equal(y,TX)
        self.assertTrue(m.all())
        self.assertEqual(l.spec,LINK.spec)

    def test_version_separation(self):
        self.bad(lambda p:p.update(format='PLM-S1-chip-observation-packet-v1'))

    def test_true_offsets_rejected(self):
        for key in ('true_cfo_hz','true_phase_rad','true_delay_chips','gold','frames','channel_seed'):
            with self.subTest(key=key): self.bad(lambda p:p.update({key:0}))

    def test_checksum_rejected(self):
        p=packet()
        p['samples']['real'][20]+=1
        with self.assertRaises(ValueError): from_packet(p)

    def test_numeric_mask_rejected(self): self.bad(lambda p:p['observed_mask'].__setitem__(20,1))
    def test_bool_chip_rejected(self): self.bad(lambda p:p['samples']['real'].__setitem__(20,True))
    def test_nan_rejected(self):
        p=packet()
        p['samples']['real'][20]=float('nan')
        with self.assertRaises(ValueError): from_packet(p)
    def test_hidden_sample_rejected(self): self.bad(lambda p:p['observed_mask'].__setitem__(20,False))
    def test_boundary_rejected(self): self.bad(lambda p:p['boundary'].update(inference_enabled=True))
    def test_invalid_norm(self): self.bad(lambda p:p['normalization'].update(pilot_amplitude=1.))
    def test_true_phase_reference(self): self.bad(lambda p:p.update(phase_reference='already_corrected'))
    def test_short_array(self): self.bad(lambda p:p['samples']['real'].pop())
    def test_extra_link_truth(self): self.bad(lambda p:p['link'].update(true_cfo_hz=0))

    def test_required_pins(self):
        for b,l in ((None,LINK),(BOOK,None)):
            with self.assertRaises(ValueError): Session(packet(),CAT,expected_book=b,expected_link=l)

    def test_wrong_pins(self):
        for b,l in ((PhaseCodebook(2048,'wrong'),LINK),(BOOK,replace(LINK,layout='edge2'))):
            with self.assertRaises(ValueError): Session(packet(),CAT,expected_book=b,expected_link=l)

    def test_actual_recovery(self):
        y,m=perturbed()
        s=Session(packet(y,m),CAT,expected_book=BOOK,expected_link=LINK)
        result=s.query(query())
        self.assertEqual(result['selected'],FRAMES[0]['slots']['subject'])
        self.assertIs(result['eligible_for_inference'],False)

    def test_all_seven_slots(self):
        y,m=perturbed()
        s=Session(packet(y,m),CAT,expected_book=BOOK,expected_link=LINK)
        for f in FRAMES:
            for role,truth in f['slots'].items():
                choices=entity_candidates() if role in ('subject','object') else CAT['vocabulary'][role]
                with self.subTest(event=f['event_id'],role=role):
                    self.assertEqual(s.query(dict(document_id=DOC,event_id=f['event_id'],role=role,candidates=choices))['selected'],truth)

    def test_digest_not_lookup(self):
        p=packet()
        p['source_digest']='a'*64
        p['payload_hash']=digest({k:v for k,v in p.items() if k!='payload_hash'})
        self.assertEqual(Session(p,CAT,expected_book=BOOK,expected_link=LINK).query(query())['selected'],FRAMES[0]['slots']['subject'])

    def test_truth_query_even_when_abstaining(self):
        p=packet(np.zeros(8480,complex),np.zeros(8480,bool))
        s=Session(p,CAT,expected_book=BOOK,expected_link=LINK)
        self.assertEqual(s.query(query())['status'],'abstain')
        with self.assertRaises(ValueError): s.query(dict(query(),true_cfo_hz=0))

    def test_sync_diagnostics_copy(self):
        s=Session(packet(),CAT,expected_book=BOOK,expected_link=LINK)
        r=s.query(query())
        r['synchronization']['pilot_observed_per_block'][0]=0
        self.assertEqual(s.synchronization['pilot_observed_per_block'][0],64)

    def test_negative_query(self):
        s=Session(packet(),CAT,expected_book=BOOK,expected_link=LINK)
        q=query()
        q['event_id']='absent-'+q['event_id']
        self.assertIsNone(s.query(q)['selected'])

    def test_nonspreading_flag(self):
        link=replace(LINK,mode='repeat')
        tx,norm=transmit(MEMORY,BOOK,link)
        s=Session(packet(tx,link=link,norm=norm),CAT,expected_book=BOOK,expected_link=link)
        self.assertIs(s.query(query())['spreading_applied'],False)


if __name__=='__main__': unittest.main()
