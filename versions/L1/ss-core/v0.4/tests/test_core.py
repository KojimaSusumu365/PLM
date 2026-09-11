import copy
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v09.component.algebra import digest
from ss_retention.memory import CorrectionMemory, ChannelMemory
from ss_retention.learning import learn as batch_learn
from ss_core.clock import ReadWindow, ExactPort, read_scores, PILOT
from ss_core.learning import learn, WriteWindow
from ss_core.memory import WaveCorrectionView
from evaluation.integrity import ROOT, read
from evaluation.ports import factory

LEX = read(ROOT/'data/lexicon.json')['slot_candidates']
KEY = digest('test-core-key')

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.memory = CorrectionMemory(LEX)
        self.teacher = {'key':KEY,'domain':'subject','value':LEX['subject'][0],'protect':True}

    def trained(self):
        self.assertEqual(learn(self.memory,self.teacher)['status'],'learned')
        return self.memory.parts['main']

    def test_batch_equivalence(self):
        batch = copy.deepcopy(self.memory)
        for i in range(6):
            t = dict(self.teacher,key=digest(str(i%3)),value=LEX['subject'][i%6])
            batch_learn(batch,t)
            self.assertEqual(learn(self.memory,t)['status'],'learned')
            for name,part in self.memory.parts.items():
                np.testing.assert_allclose(part.weights,batch.parts[name].weights,atol=1e-10,rtol=1e-10)

    def test_no_legacy_batch_fallback(self):
        with patch.object(ChannelMemory,'scores',side_effect=AssertionError('batch scorer used')):
            self.trained()
            r = WaveCorrectionView(self.memory).recall(KEY,'subject')
            self.assertEqual(r['value'],self.teacher['value'])

    def test_chunk_bitwise_equal(self):
        part = self.trained()
        a,_ = read_scores(part,KEY,'test',chunk=1)
        for chunk in (17,37,64,1024):
            b,_ = read_scores(part,KEY,'test',chunk=chunk)
            np.testing.assert_array_equal(a,b)

    def test_phase_is_estimated(self):
        part = self.trained()
        a,_ = read_scores(part,KEY,'test')
        b,audit = read_scores(part,KEY,'test',port_factory=factory('phase'))
        self.assertEqual(audit['status'],'ready')
        np.testing.assert_allclose(a,b,atol=1e-10,rtol=1e-10)

    def test_partial_query_but_no_partial_learning(self):
        part = self.trained()
        a,audit = read_scores(part,KEY,'test',port_factory=factory('drop25'))
        self.assertIsNotNone(a)
        self.assertEqual(audit['data_counts'],[552]*4)
        before = self.memory.fingerprint
        result = learn(self.memory,self.teacher,port_factory=factory('drop25'))
        self.assertEqual(result['status'],'held')
        self.assertEqual(self.memory.fingerprint,before)

    def test_faults_hold_and_unchanged(self):
        self.trained()
        before = self.memory.fingerprint
        for condition in ('drop50','pilot_missing','tail_drift','truncate','reorder'):
            with self.subTest(condition=condition):
                self.assertEqual(learn(self.memory,self.teacher,port_factory=factory(condition))['status'],'held')
                self.assertEqual(WaveCorrectionView(self.memory,factory(condition)).recall(KEY,'subject')['status'],'waveform_hold')
                self.assertEqual(self.memory.fingerprint,before)

    def test_no_decision_before_tail(self):
        part = self.trained()
        w = ReadWindow(part,KEY,'test')
        events = iter(ExactPort(part,KEY,'test'))
        for _ in range(PILOT+part.dimension):
            w.push(*next(events))
        self.assertEqual(w.peek()['status'],'provisional')
        self.assertFalse(w.peek()['eligible_for_decision'])
        self.assertNotIn('scores',w.peek())
        scores,audit = w.finish()
        self.assertIsNone(scores)
        self.assertEqual(audit['reason'],'incomplete_window')

    def test_no_future_sample_access(self):
        part = self.trained()
        w = ReadWindow(part,KEY,'test')
        events = iter(ExactPort(part,KEY,'test'))
        for _ in range(PILOT+1):
            w.push(*next(events))
        expected = part.values[:,:,0].conj() * (part.weights[:,0]*part.context(KEY)[:,0].conj())[:,None]
        np.testing.assert_array_equal(w.acc,expected)
        self.assertEqual(w.counts.tolist(),[1]*4)

    def test_missing_write_ack_atomic(self):
        self.trained()
        before = self.memory.fingerprint
        r = learn(self.memory,self.teacher,ack=lambda name,tick:not(name=='protected' and tick==600))
        self.assertEqual(r['status'],'held')
        self.assertEqual(self.memory.fingerprint,before)

    def test_stale_commit_does_not_overwrite_new_state(self):
        self.trained()
        expected = copy.deepcopy(self.memory)
        newer = dict(self.teacher,key=digest('other'),value=LEX['subject'][1])
        learn(expected,newer)
        r = learn(self.memory,self.teacher,before_commit=lambda:learn(self.memory,newer))
        self.assertEqual(r['reason'],'stale_memory')
        self.assertEqual(self.memory.fingerprint,expected.fingerprint)

    def test_read_detects_memory_mutation(self):
        part = self.trained()
        w = ReadWindow(part,KEY,'test')
        w.push_many(ExactPort(part,KEY,'test'))
        part.weights[0,0] += 1
        self.assertEqual(w.finish()[1]['reason'],'memory_changed_during_read')

    def test_unregistered_never_accepted(self):
        part = self.trained()
        for p in self.memory.parts.values():
            p.registry.clear()
        self.assertEqual(WaveCorrectionView(self.memory).recall(KEY,'subject')['status'],'unregistered')

    def test_coefficients_are_required(self):
        self.trained()
        for p in self.memory.parts.values():
            p.weights[:] = 0
        self.assertIsNone(WaveCorrectionView(self.memory).recall(KEY,'subject')['value'])

    def test_wrong_external_teacher_can_be_learned_and_corrected(self):
        wrong = dict(self.teacher,value=LEX['subject'][1])
        learn(self.memory,wrong)
        self.assertEqual(WaveCorrectionView(self.memory).recall(KEY,'subject')['value'],wrong['value'])
        learn(self.memory,self.teacher)
        self.assertEqual(WaveCorrectionView(self.memory).recall(KEY,'subject')['value'],self.teacher['value'])

    def test_invalid_sample_contracts(self):
        part = self.memory.parts['main']
        for sample,mask in [(np.array([np.nan]*4),np.ones(4,bool)),(np.ones(4),np.zeros(4,bool)),
                            (np.ones(3),np.ones(4,bool)),(np.ones(4),np.ones(4,int))]:
            w = ReadWindow(part,KEY,'test')
            w.push(0,sample,mask)
            self.assertIsNone(w.finish()[0])

    def test_duplicate_extra_and_closed_ticks(self):
        part = self.memory.parts['main']
        event = next(iter(ExactPort(part,KEY,'test')))
        w = ReadWindow(part,KEY,'test')
        w.push(*event)
        w.push(*event)
        self.assertIsNone(w.finish()[0])
        w = ReadWindow(part,KEY,'test')
        w.push_many(ExactPort(part,KEY,'test'))
        self.assertIsNotNone(w.finish()[0])
        self.assertIsNone(w.finish()[0])

    def test_invalid_write_and_incomplete_write(self):
        for event in [(1,np.ones(4),True),(0,np.ones(3),True),(0,np.ones(4),False),(0,np.full(4,np.nan),True)]:
            w = WriteWindow(self.memory.parts['main'])
            w.push(*event)
            self.assertIsNone(w.finish()[0])
        w = WriteWindow(self.memory.parts['main'])
        w.push(0,np.ones(4),True)
        self.assertEqual(w.finish()[1]['reason'],'incomplete_write')

    def test_invalid_teacher_and_chunk(self):
        for teacher in [dict(self.teacher,extra=1),dict(self.teacher,value='unknown'),dict(self.teacher,protect=1)]:
            with self.assertRaises(ValueError):
                learn(self.memory,teacher)
        for chunk in (0,1025,True):
            with self.assertRaises(ValueError):
                read_scores(self.memory.parts['main'],KEY,'test',chunk=chunk)

    def test_wrong_window_reference_held(self):
        part = self.trained()
        w = ReadWindow(part,KEY,'expected-window')
        w.push_many(ExactPort(part,KEY,'different-window'))
        self.assertIsNone(w.finish()[0])

    def test_pilot_missing_boundary(self):
        part = self.trained()
        for missing,expected in ((4,'ready'),(5,'held')):
            w = ReadWindow(part,KEY,'test')
            for tick,y,mask in ExactPort(part,KEY,'test'):
                if tick<missing or PILOT+part.dimension<=tick<PILOT+part.dimension+missing:
                    y[:]=0
                    mask[:]=False
                w.push(tick,y,mask)
            self.assertEqual(w.finish()[1]['status'],expected)

    def test_pilot_gain_mismatch_held(self):
        part = self.trained()
        w = ReadWindow(part,KEY,'test')
        for tick,y,mask in ExactPort(part,KEY,'test'):
            w.push(tick,y*1.2,mask)
        self.assertIsNone(w.finish()[0])

if __name__ == '__main__':
    unittest.main()
