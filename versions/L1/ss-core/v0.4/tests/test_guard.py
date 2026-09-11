import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from plm_l1_v09.component.algebra import digest
from ss_retention.memory import CorrectionMemory,ChannelMemory
from ss_core.learning import learn as old_learn
from ss_core.memory import WaveCorrectionView
from ss_core_v02.learning import learn
from ss_core_v02.store import Store,scope_id
from ss_core_v02.transaction import apply_packet,apply_received
from ss_core_v02.runtime import generate_packet
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from evaluation.integrity import ROOT,read
from evaluation.faults import Acquisitions
from bridge.carrier import encode

LEX=read(ROOT/'data/lexicon.json')['slot_candidates']
KEY=digest('guard-unit')

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.memory=CorrectionMemory(LEX)
        self.teacher={'key':KEY,'domain':'subject','value':LEX['subject'][0],'protect':True}

    def test_clean_numerical_equivalence(self):
        old=copy.deepcopy(self.memory);old_learn(old,self.teacher)
        for method in ('single','mean4','unchecked','guard'):
            m=copy.deepcopy(self.memory);r=learn(m,self.teacher,method=method)
            self.assertEqual(r['status'],'learned')
            for name,p in m.parts.items():np.testing.assert_allclose(p.weights,old.parts[name].weights,atol=1e-10,rtol=1e-10)

    def test_no_batch_scorer(self):
        with patch.object(ChannelMemory,'scores',side_effect=AssertionError('batch scorer')):
            self.assertEqual(learn(self.memory,self.teacher)['status'],'learned')

    def test_new_windows_and_budget(self):
        for method,windows in [('single',2),('mean4',8),('unchecked',8),('guard',8)]:
            port=Acquisitions('clean');m=copy.deepcopy(self.memory)
            r=learn(m,self.teacher,method=method,port_factory=port)
            self.assertEqual(r['cost']['read_windows_started'],windows)
            self.assertEqual(port.calls,windows)
            self.assertEqual(r['cost']['read_ticks_processed'],windows*768)
            self.assertEqual(r['cost']['write_ticks_acknowledged'],2*736)

    def test_independent_noise_hold_before_write(self):
        before=self.memory.fingerprint
        r=learn(self.memory,self.teacher,port_factory=Acquisitions('independent16'))
        self.assertEqual(r['reason'],'pre_disagreement')
        self.assertEqual(r['cost']['write_ticks_acknowledged'],0)
        self.assertEqual(self.memory.fingerprint,before)

    def test_shared_pre_noise_fails_postcheck(self):
        before=self.memory.fingerprint
        r=learn(self.memory,self.teacher,port_factory=Acquisitions('pre_shared16'))
        self.assertEqual(r['reason'],'post_inconsistency')
        self.assertGreater(r['cost']['write_ticks_acknowledged'],0)
        self.assertEqual(self.memory.fingerprint,before)

    def test_post_only_noise_hold(self):
        before=self.memory.fingerprint
        r=learn(self.memory,self.teacher,port_factory=Acquisitions('post_noise16'))
        self.assertEqual(r['reason'],'post_inconsistency')
        self.assertEqual(self.memory.fingerprint,before)

    def test_post_truncation_hold(self):
        before=self.memory.fingerprint
        r=learn(self.memory,self.teacher,port_factory=Acquisitions('post_truncate'))
        self.assertEqual(r['reason'],'post_window')
        self.assertEqual(self.memory.fingerprint,before)

    def test_shared_coherent_bias_is_not_authenticated(self):
        p=Acquisitions('coherent_bias',bias_labels={KEY:('subject',self.teacher['value'])})
        r=learn(self.memory,self.teacher,port_factory=p)
        self.assertEqual(r['status'],'learned')
        self.assertNotEqual(WaveCorrectionView(self.memory).recall(KEY,'subject')['value'],self.teacher['value'])

    def test_legitimate_correction_not_rejected_for_old_disagreement(self):
        old=dict(self.teacher,value=LEX['subject'][1]);old_learn(self.memory,old)
        r=learn(self.memory,self.teacher)
        self.assertEqual(r['status'],'learned')
        self.assertEqual(WaveCorrectionView(self.memory).recall(KEY,'subject')['value'],self.teacher['value'])

    def test_wrong_external_teacher_still_learned(self):
        wrong=dict(self.teacher,value=LEX['subject'][1])
        self.assertEqual(learn(self.memory,wrong)['status'],'learned')
        self.assertEqual(WaveCorrectionView(self.memory).recall(KEY,'subject')['value'],wrong['value'])

    def test_write_failure_atomic(self):
        before=self.memory.fingerprint
        r=learn(self.memory,self.teacher,ack=lambda part,tick:not(part=='protected' and tick==500))
        self.assertEqual(r['reason'],'write_window');self.assertEqual(self.memory.fingerprint,before)

    def test_stale_before_commit(self):
        newer=dict(self.teacher,key=digest('newer'))
        expected=copy.deepcopy(self.memory);old_learn(expected,newer)
        r=learn(self.memory,self.teacher,before_commit=lambda:old_learn(self.memory,newer))
        self.assertEqual(r['reason'],'stale_memory');self.assertEqual(self.memory.fingerprint,expected.fingerprint)

    def test_chunk_identical(self):
        other=copy.deepcopy(self.memory)
        learn(self.memory,self.teacher,chunk=1);learn(other,self.teacher,chunk=37)
        self.assertEqual(self.memory.fingerprint,other.fingerprint)

    def test_method_contract(self):
        with self.assertRaises(ValueError):learn(self.memory,self.teacher,method='bogus')

class StoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=PartialModel.load(ROOT/'model')
        cls.case=read(ROOT/'data/GUARD_CORPUS.json')['splits']['development'][0]
    def setUp(self):
        self.store=Store(RevisionMemory(self.model.codec.candidates))
        self.initial=self.model.encode(self.case['initial']);self.final=self.model.encode(self.case['known'])
        self.query=self.model.encode(self.case['query']);self.scope=self.case['scope']
        self.store,r=apply_packet(self.model,self.store,self.scope,self.initial)
        self.assertEqual(r['status'],'learned')

    def test_pending_blocks_stale_cold_generation(self):
        before=self.store.memory.fingerprint
        held,r=apply_packet(self.model,self.store,self.scope,self.final,port_factory=Acquisitions('independent16'))
        self.assertEqual(r['status'],'held');self.assertEqual(held.memory.fingerprint,before)
        self.assertEqual(len(held.pending),1)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'store';held.save(p);cold=Store.load(p,self.model.codec.candidates)
        self.assertEqual(generate_packet(self.model,cold,self.scope,self.query)['status'],'needs_confirmation')
        self.assertNotIn('text',generate_packet(self.model,cold,self.scope,self.query))

    def test_clean_reconfirmation_clears_pending(self):
        held,_=apply_packet(self.model,self.store,self.scope,self.final,port_factory=Acquisitions('independent16'))
        updated,r=apply_packet(self.model,held,self.scope,self.final)
        self.assertEqual(r['status'],'learned');self.assertEqual(updated.pending,set())
        self.assertEqual(generate_packet(self.model,updated,self.scope,self.query)['status'],'generated')

    def test_external_bad_sync_records_pending(self):
        wire=encode(self.model,self.final,'expected')
        held,r=apply_received(self.model,self.store,self.scope,wire,'wrong')
        self.assertEqual(r['status'],'rejected');self.assertEqual(held.memory.fingerprint,self.store.memory.fingerprint)
        self.assertIn(scope_id(self.scope),held.pending)

    def test_incomplete_teacher_does_not_update(self):
        held,r=apply_packet(self.model,self.store,self.scope,self.query)
        self.assertEqual(r['status'],'rejected');self.assertEqual(held.memory.fingerprint,self.store.memory.fingerprint)

    def test_second_target_failure_rolls_back_all_coefficients(self):
        count=[0]
        def ack(name,tick):
            count[0]+=1;return count[0]!=1472+50
        held,r=apply_packet(self.model,self.store,self.scope,self.final,ack=ack)
        self.assertEqual(r['status'],'held');self.assertEqual(held.memory.fingerprint,self.store.memory.fingerprint)
        self.assertEqual(r['receipts'][0]['status'],'confirmed')

    def test_pending_has_no_answer_values(self):
        held,_=apply_packet(self.model,self.store,self.scope,self.final,port_factory=Acquisitions('independent16'))
        self.assertEqual(held.pending,{scope_id(self.scope)})

    def test_pending_scope_is_order_invariant(self):
        other={'episode':self.scope['episode'],'mutable':self.scope['mutable'][::-1]}
        self.assertEqual(scope_id(other),scope_id(self.scope))

    def test_coefficient_zero_still_cannot_generate(self):
        learned,_=apply_packet(self.model,self.store,self.scope,self.final)
        for p in learned.memory.ss.parts.values():p.weights[:]=0
        self.assertNotEqual(generate_packet(self.model,learned,self.scope,self.query)['status'],'generated')

    def test_all_development_target_domains_correctable(self):
        cases=[c for c in read(ROOT/'data/GUARD_CORPUS.json')['splits']['development'] if c['kind']=='focal']
        for c in cases:
            with self.subTest(case=c['id']):
                s=Store(RevisionMemory(self.model.codec.candidates))
                s,r=apply_packet(self.model,s,c['scope'],self.model.encode(c['initial']))
                self.assertEqual(r['status'],'learned')
                s,r=apply_packet(self.model,s,c['scope'],self.model.encode(c['known']))
                self.assertEqual(r['status'],'learned')
                self.assertEqual(generate_packet(self.model,s,c['scope'],self.model.encode(c['query']))['status'],'generated')

if __name__=='__main__':unittest.main()
