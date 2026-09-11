import copy,tempfile,unittest
from pathlib import Path
import numpy as np
from bridge.carrier import encode,validate,carrier,demodulate,budget,profile
from bridge.runtime import receive,generate_received
from bridge.learning import learn_received
from bridge.recovery import recover_masked
from evaluation.integrity import ROOT,read
from evaluation.channel import channel,control_receive
from ss_partial.runtime import PartialModel
from ss_partial.contract import cell
from ss_revision.memory import RevisionMemory

class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=PartialModel.load(ROOT/'model');cls.case=read(ROOT/'data/CORPUS.json')['splits']['development'][0]
        cls.known=cls.model.encode(cls.case['known']);cls.query=cls.model.encode(cls.case['query'])
        cls.tx=encode(cls.model,cls.known,'test-teacher');cls.rx,cls.truth=channel(cls.model,cls.tx,'offset_noise',1100)
        cls.qtx=encode(cls.model,cls.query,'test-query');cls.qrx,_=channel(cls.model,cls.qtx,'partial25',11100)
        cls.memory,cls.teaching=learn_received(cls.model,RevisionMemory(cls.model.codec.candidates),cls.case['scope'],cls.rx,'test-teacher')

    def test_profile_dimension(self):self.assertEqual(profile(self.model)['dimension'],8192)
    def test_unit_phase_and_inverse(self):
        c=carrier(self.model);np.testing.assert_allclose(abs(c),1,atol=1e-15)
        v=self.model.vector(self.known);np.testing.assert_allclose(v*c*c.conj(),v,atol=1e-14)
    def test_energy_budget(self):
        self.assertEqual(budget()['total_chips'],33920)
        for f in self.tx['frames']:self.assertAlmostEqual(float(np.sum(np.asarray(f['real'])**2+np.asarray(f['imag'])**2)),57344,places=7)
    def test_clean_exact_numeric_roundtrip(self):
        v,m,a=demodulate(self.model,self.tx,'test-teacher');self.assertTrue(m.all());np.testing.assert_allclose(v,self.model.vector(self.known),atol=1e-13)
    def test_offset_recovery(self):
        r=receive(self.model,self.rx,'test-teacher');self.assertEqual(r['status'],'received')
        self.assertEqual(self.model.recover(r['packet'])['observation'],self.case['known'])
    def test_partial_recovery_retains_observed(self):
        v,m,_=demodulate(self.model,self.qrx,'test-query');p,a=recover_masked(self.model,v,m)
        self.assertLess(int(m.sum()),8192);np.testing.assert_array_equal(self.model.vector(p)[m],v[m]);self.assertTrue(a['observed_values_retained_exactly'])
        self.assertEqual(self.model.recover(p)['observation'],self.case['query'])
    def test_two_missing_targets_not_invented(self):
        r=receive(self.model,self.qrx,'test-query');o=self.model.recover(r['packet'])['observation']
        self.assertTrue(all(o['cells'][t]==cell('unobserved',[]) for t in self.case['scope']['mutable']))
    def test_too_few_coordinates(self):
        with self.assertRaises(ValueError):recover_masked(self.model,np.zeros(8192,complex),np.zeros(8192,bool))
    def test_masked_values_cannot_hide_evidence(self):
        with self.assertRaises(ValueError):recover_masked(self.model,np.ones(8192,complex),np.zeros(8192,bool))
    def test_zero_signal_rejected(self):
        with self.assertRaises(ValueError):recover_masked(self.model,np.zeros(8192,complex),np.ones(8192,bool))
    def test_unknown_wire_field(self):
        p=copy.deepcopy(self.tx);p['gold']=self.case['known'];self.assertEqual(receive(self.model,p,'test-teacher')['stage'],'contract')
    def test_true_offsets_refused(self):
        p=copy.deepcopy(self.tx);p['phase_rad']=.73;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_wrong_message_id(self):self.assertEqual(receive(self.model,self.tx,'other')['status'],'rejected')
    def test_wrong_model_fingerprint(self):
        p=copy.deepcopy(self.tx);p['model_fingerprint']='0'*64;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_wrong_profile(self):
        p=copy.deepcopy(self.tx);p['profile_fingerprint']='0'*64;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_nonfinite_chips(self):
        p=copy.deepcopy(self.tx);p['frames'][0]['real'][17]=float('nan');self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_boolean_numeric_chip(self):
        p=copy.deepcopy(self.tx);p['frames'][0]['real'][17]=True;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_integer_mask_refused(self):
        p=copy.deepcopy(self.tx);p['frames'][0]['observed'][17]=1;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_hidden_coordinate_nonzero_refused(self):
        p=copy.deepcopy(self.tx);p['frames'][0]['observed'][17]=False;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_duplicate_frame_index(self):
        p=copy.deepcopy(self.tx);p['frames'][1]['index']=0;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_missing_frame(self):
        p=copy.deepcopy(self.tx);p['frames'].pop();self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_wrong_normalization(self):
        p=copy.deepcopy(self.tx);p['frames'][0]['normalization']['pilot_amplitude']*=2;self.assertEqual(receive(self.model,p,'test-teacher')['status'],'rejected')
    def test_repeat_requires_explicit_mode(self):
        p=encode(self.model,self.known,'repeat','repeat');self.assertEqual(receive(self.model,p,'repeat')['status'],'rejected')
        self.assertEqual(receive(self.model,p,'repeat','repeat')['status'],'received')
    def test_frame_swap_fails_pilot_binding(self):
        p,_=channel(self.model,self.tx,'frame_swap',1100);self.assertEqual(receive(self.model,p,'test-teacher')['stage'],'synchronization')
    def test_pilot_erasure_holds(self):
        p,_=channel(self.model,self.tx,'pilot_missing',1100);self.assertEqual(receive(self.model,p,'test-teacher')['stage'],'synchronization')
    def test_valid_pilots_empty_payload_not_meaning(self):
        p,_=channel(self.model,self.tx,'payload_missing',1100);r=receive(self.model,p,'test-teacher')
        self.assertTrue(all(f['sync']['status']=='aligned' for f in r['frames']));self.assertEqual(r['stage'],'meaning_recovery')
    def test_disable_sync_fails_offset(self):
        r=control_receive(self.model,self.rx,'test-teacher','ss_disabled',self.truth);self.assertNotEqual(r['status'],'received')
    def test_oracle_is_separate_reference(self):
        r=control_receive(self.model,self.rx,'test-teacher','ss_oracle',self.truth);self.assertEqual(r['status'],'received')
    def test_external_teacher_updates_two_targets(self):
        self.assertEqual(self.teaching['status'],'learned');self.assertEqual(len(self.teaching['receipts']),2)
        self.assertEqual(self.teaching['received_observation'],self.case['known'])
    def test_learning_does_not_mutate_original(self):
        memory=RevisionMemory(self.model.codec.candidates);fp=memory.fingerprint
        updated,r=learn_received(self.model,memory,self.case['scope'],self.rx,'test-teacher')
        self.assertEqual(memory.fingerprint,fp);self.assertNotEqual(updated.fingerprint,fp)
    def test_rejected_teacher_no_update(self):
        p,_=channel(self.model,self.tx,'pilot_missing',1100);fp=self.memory.fingerprint
        updated,r=learn_received(self.model,self.memory,self.case['scope'],p,'test-teacher');self.assertEqual(updated.fingerprint,fp)
    def test_incomplete_teacher_not_self_training(self):
        updated,r=learn_received(self.model,self.memory,self.case['scope'],self.qtx,'test-query')
        self.assertEqual(r['status'],'rejected');self.assertEqual(updated.fingerprint,self.memory.fingerprint)
    def test_scope_error_atomic(self):
        scope=copy.deepcopy(self.case['scope']);scope['mutable'][1]='event:9/object';fp=self.memory.fingerprint
        updated,r=learn_received(self.model,self.memory,scope,self.rx,'test-teacher');self.assertEqual(updated.fingerprint,fp);self.assertEqual(r['status'],'rejected')
    def test_cold_generation_no_teacher_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'memory';self.memory.save(p);memory=RevisionMemory.load(p,self.model.codec.candidates)
            g=generate_received(self.model,memory,self.case['scope'],self.qrx,'test-query')
        self.assertEqual(g['status'],'generated');self.assertTrue(g['fresh_session_no_receipts'])
    def test_zero_ss_weights_prevents_completion(self):
        memory=copy.deepcopy(self.memory)
        for part in memory.ss.parts.values():part.weights[:]=0
        g=generate_received(self.model,memory,self.case['scope'],self.qtx,'test-query');self.assertEqual(g['status'],'needs_confirmation')
    def test_no_memory_prevents_completion(self):
        g=generate_received(self.model,RevisionMemory(self.model.codec.candidates),self.case['scope'],self.qtx,'test-query')
        self.assertNotEqual(g['status'],'generated')
    def test_conflict_state_preserved_not_auto_resolved(self):
        o=copy.deepcopy(self.case['query']);t=self.case['scope']['mutable'][0];choices=self.model.codec.choices[t]
        o['cells'][t]=cell('conflict',list(choices[:2]));p=encode(self.model,self.model.encode(o),'conflict')
        r=receive(self.model,p,'conflict');self.assertEqual(self.model.recover(r['packet'])['observation']['cells'][t]['state'],'conflict')
        self.assertEqual(generate_received(self.model,self.memory,self.case['scope'],p,'conflict')['status'],'needs_confirmation')
    def test_ambiguous_state_preserved(self):
        o=copy.deepcopy(self.case['query']);t=self.case['scope']['mutable'][0];o['cells'][t]=cell('ambiguous',list(self.model.codec.choices[t][:2]))
        p=encode(self.model,self.model.encode(o),'ambiguous');r=receive(self.model,p,'ambiguous')
        self.assertEqual(self.model.recover(r['packet'])['observation']['cells'][t]['state'],'ambiguous')
    def test_valid_wrong_teacher_can_be_learned(self):
        o=copy.deepcopy(self.case['known']);t=self.case['scope']['mutable'][0]
        v=next(v for v in self.model.codec.choices[t] if v!=o['cells'][t]['candidates'][0]);o['cells'][t]=cell('known',[v])
        p=encode(self.model,self.model.encode(o),'untrusted-teacher');memory,r=learn_received(self.model,RevisionMemory(self.model.codec.candidates),self.case['scope'],p,'untrusted-teacher')
        self.assertEqual(r['status'],'learned');self.assertEqual(r['received_observation']['cells'][t],cell('known',[v]))
    def test_sampling_alias_not_identifiable(self):
        p,_=channel(self.model,self.tx,'sampling_alias',1100)
        r=receive(self.model,p,'test-teacher');self.assertEqual(r['status'],'received')
        self.assertTrue(all(abs(f['sync']['estimated_cfo_hz']-.1)<.025 for f in r['frames']))

if __name__=='__main__':unittest.main()
