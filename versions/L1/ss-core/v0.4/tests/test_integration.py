import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin, request, prepare
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import complete
from bridge.carrier import encode
from ss_core.learning import learn_packet, learn_received, learn_revision
from ss_core.runtime import generate_received
from ss_core.memory import WaveRevisionView
from evaluation.integrity import ROOT, read
from evaluation.ports import factory
from evaluation.oracle import localize, scored

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = PartialModel.load(ROOT/'model')
        cls.case = read(ROOT/'data/CORPUS.json')['splits']['development'][0]
        cls.teacher_packet = cls.model.encode(cls.case['known'])
        cls.query_packet = cls.model.encode(cls.case['query'])

    def setUp(self):
        self.memory = RevisionMemory(self.model.codec.candidates)

    def teach(self):
        self.memory,r = learn_packet(self.model,self.memory,self.case['scope'],self.teacher_packet)
        self.assertEqual(r['status'],'learned')

    def test_bridge_teacher_to_cold_waveform_generation(self):
        wire = encode(self.model,self.teacher_packet,'test-teacher','spread')
        self.memory,r = learn_received(self.model,self.memory,self.case['scope'],wire,'test-teacher',chunk=37)
        self.assertEqual(r['status'],'learned')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'memory'
            self.memory.save(p)
            cold = RevisionMemory.load(p,self.model.codec.candidates)
        wire = encode(self.model,self.query_packet,'test-query','spread')
        for order,goals in [('preserve',['subject','subject']),('reverse',['object','subject'])]:
            r = generate_received(self.model,cold,self.case['scope'],wire,'test-query',order=order,goals=goals)
            self.assertEqual(r['status'],'generated')
            ids = self.case['meaning']['presentation'][::1 if order=='preserve' else -1]
            self.assertTrue(all(scored(localize(self.case['meaning'],ids,goals),r['text']).values()))
            self.assertTrue(r['fresh_session_no_receipts'])
            self.assertEqual(cold.fingerprint,self.memory.fingerprint)

    def test_incomplete_teacher_rejected(self):
        before = self.memory.fingerprint
        wire = encode(self.model,self.query_packet,'partial-teacher','spread')
        m,r = learn_received(self.model,self.memory,self.case['scope'],wire,'partial-teacher')
        self.assertEqual(r['status'],'rejected')
        self.assertIs(m,self.memory)
        self.assertEqual(m.fingerprint,before)

    def test_bad_external_id_rejected(self):
        wire = encode(self.model,self.teacher_packet,'right','spread')
        m,r = learn_received(self.model,self.memory,self.case['scope'],wire,'wrong')
        self.assertEqual(r['status'],'rejected')
        self.assertIs(m,self.memory)

    def test_second_target_failure_rolls_back_roots_and_weights(self):
        before = self.memory.fingerprint
        count = [0]
        def ack(name,tick):
            count[0] += 1
            return count[0] != 2*736+70
        m,r = learn_packet(self.model,self.memory,self.case['scope'],self.teacher_packet,ack=ack)
        self.assertEqual(r['status'],'held')
        self.assertEqual(r['receipts'][0]['status'],'confirmed')
        self.assertEqual(m.fingerprint,before)
        self.assertEqual(m.roots,{})

    def test_no_fallback_to_old_learner(self):
        with (patch('ss_revision.learning.learn',side_effect=AssertionError('old revision learn')),
              patch('ss_retention.learning.learn',side_effect=AssertionError('old SS learn'))):
            self.teach()

    def test_stale_prepared_revision(self):
        begin(self.model,self.memory,self.case['scope'],self.teacher_packet)
        t = self.case['scope']['mutable'][0]
        msg = request(self.model,self.memory,self.case['scope'],self.teacher_packet,t,self.case['known']['cells'][t]['candidates'][0])
        teacher,_ = prepare(self.model,self.memory,self.case['scope'],self.teacher_packet,msg)
        self.assertEqual(learn_revision(self.memory,teacher)['status'],'confirmed')
        before = self.memory.fingerprint
        with self.assertRaises(ValueError):
            learn_revision(self.memory,teacher)
        self.assertEqual(self.memory.fingerprint,before)

    def test_generation_holds_on_internal_bad_sync(self):
        self.teach()
        view = WaveRevisionView(self.memory,factory('tail_drift'))
        r = complete(self.model,view,Session(self.model,view,self.case['scope'],self.query_packet))
        self.assertEqual(r['status'],'needs_confirmation')
        self.assertNotIn('packet',r)

    def test_generation_requires_weights_not_revision_metadata(self):
        self.teach()
        for part in self.memory.ss.parts.values():
            part.weights[:] = 0
        view = WaveRevisionView(self.memory)
        r = complete(self.model,view,Session(self.model,view,self.case['scope'],self.query_packet))
        self.assertEqual(r['status'],'needs_confirmation')

    def test_wrong_valid_teacher_is_not_truth_authenticated(self):
        wrong = copy.deepcopy(self.case['known'])
        t = self.case['scope']['mutable'][0]
        wrong['cells'][t]['candidates'] = [next(v for v in self.model.codec.choices[t] if v != wrong['cells'][t]['candidates'][0])]
        self.memory,r = learn_packet(self.model,self.memory,self.case['scope'],self.model.encode(wrong))
        self.assertEqual(r['status'],'learned')
        view = WaveRevisionView(self.memory)
        out = complete(self.model,view,Session(self.model,view,self.case['scope'],self.query_packet))
        self.assertEqual(out['status'],'completed')
        self.assertEqual(self.model.recover(out['packet'])['observation'],wrong)

if __name__ == '__main__':
    unittest.main()
