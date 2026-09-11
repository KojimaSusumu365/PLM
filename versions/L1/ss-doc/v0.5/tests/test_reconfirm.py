import copy,tempfile,unittest
from pathlib import Path
from evaluation.integrity import ROOT
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.contract import cell
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin,request,teach
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import assess,complete,generate
from ss_reconfirm.learning import confirm

TEXT='太郎が花子を助けた。その後、由紀が健太を褒めた。'
A='event:1/subject';B='event:1/object';SCOPE={'episode':'confirmation-unit','mutable':[A,B]}

class ReconfirmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=PartialModel.load(ROOT/'model');cls.packet=read(cls.model,[TEXT])['packet']

    def memory(self,weak=False):
        m=RevisionMemory(self.model.codec.candidates,'versioned_pair','confirm-unit');begin(self.model,m,SCOPE,self.packet)
        for t,v in ((A,'entity:由紀'),(B,'entity:健太')):teach(self.model,m,SCOPE,self.packet,request(self.model,m,SCOPE,self.packet,t,v))
        if weak:
            for part in m.ss.parts.values():part.weights[:]=0
        return m

    def session(self,m,kind='known'):
        o=copy.deepcopy(self.model.recover(self.packet)['observation'])
        if kind in ('old','old_partial'):o['cells'][A]=cell('known',['entity:花子'])
        if kind in ('missing','old_partial'):o['cells'][B]=cell('unobserved',[])
        if kind=='missing':o['cells'][A]=cell('unobserved',[])
        if kind=='conflict':o['cells'][A]=cell('conflict',['entity:由紀','entity:花子'])
        return Session(self.model,m,SCOPE,self.model.encode(o))

    def answer_all(self,m,s,policy='ss_selective'):
        for _ in range(2):
            plan=assess(self.model,m,s,policy)
            if plan['status']=='ready':break
            q=plan['questions'][0];s,_=confirm(self.model,m,s,q,'entity:由紀' if q['target']==A else 'entity:健太',policy)
        return s

    def test_strong_current_observation_needs_no_confirmation(self):
        m=self.memory();self.assertEqual(assess(self.model,m,self.session(m))['status'],'ready')

    def test_strong_missing_values_can_be_recalled(self):
        m=self.memory();self.assertEqual(generate(self.model,m,self.session(m,'missing'))['text'],TEXT)

    def test_weak_explicit_values_request_confirmation(self):
        m=self.memory(True);p=assess(self.model,m,self.session(m));self.assertEqual(len(p['questions']),2)
        self.assertTrue(all(q['reason']=='unverified_explicit_value' for q in p['questions']))

    def test_legacy_weak_explicit_fallback_reproduces_error(self):
        m=self.memory(True);s=self.session(m,'old');self.assertIn('花子が健太を',generate(self.model,m,s,'legacy')['text'])
        self.assertEqual(generate(self.model,m,s)['status'],'needs_confirmation')

    def test_always_policy_asks_even_for_strong_support(self):
        m=self.memory();self.assertEqual(len(assess(self.model,m,self.session(m),'always')['questions']),2)

    def test_conflict_is_first_priority(self):
        m=self.memory(True);s=self.session(m,'conflict');self.assertEqual(assess(self.model,m,s)['questions'][0]['target'],A)

    def test_known_disagreement_does_not_silently_overwrite(self):
        m=self.memory();s=self.session(m,'old');original=copy.deepcopy(s.packet);p=complete(self.model,m,s)
        self.assertEqual(p['questions'][0]['reason'],'explicit_value_disagrees');self.assertEqual(s.packet,original)

    def test_confirmation_changes_memory_and_numeric_packet(self):
        m=self.memory();s=self.session(m,'old');fp=m.fingerprint;q=assess(self.model,m,s)['questions'][0]
        new,r=confirm(self.model,m,s,q,'entity:由紀');self.assertNotEqual(fp,m.fingerprint)
        self.assertTrue(r['local_audit']['other_cells_unchanged']);self.assertEqual(generate(self.model,m,new)['text'],TEXT)

    def test_one_confirmed_target_does_not_authorize_other(self):
        m=self.memory(True);s=self.session(m,'old_partial');q=assess(self.model,m,s)['questions'][0]
        new,_=confirm(self.model,m,s,q,'entity:由紀');p=assess(self.model,m,new,'always')
        self.assertEqual([q['target'] for q in p['questions']],[B])

    def test_two_confirmations_complete_always_policy(self):
        m=self.memory();s=self.answer_all(m,self.session(m),'always');self.assertEqual(generate(self.model,m,s,'always')['text'],TEXT)

    def test_receipt_is_not_used_on_fresh_requery(self):
        m=self.memory(True);s=self.answer_all(m,self.session(m,'old'));self.assertEqual(len(s.confirmed),2)
        fresh=self.session(m,'missing');self.assertEqual(fresh.confirmed,{})
        self.assertEqual(generate(self.model,m,fresh)['text'],TEXT)

    def test_zeroed_ss_after_confirmation_cannot_recall_cold(self):
        m=self.memory(True);s=self.answer_all(m,self.session(m,'old'))
        for p in m.ss.parts.values():p.weights[:]=0
        self.assertEqual(generate(self.model,m,self.session(m,'missing'))['status'],'needs_confirmation')

    def test_stale_question_rejected_without_second_update(self):
        m=self.memory(True);s=self.session(m);q=assess(self.model,m,s)['questions'][0];new,_=confirm(self.model,m,s,q,'entity:由紀');fp=m.fingerprint
        with self.assertRaises(ValueError):confirm(self.model,m,new,q,'entity:由紀')
        self.assertEqual(m.fingerprint,fp)

    def test_unrequested_target_rejected(self):
        m=self.memory();s=self.session(m,'old');q=copy.deepcopy(assess(self.model,m,s)['questions'][0]);q['target']=B;fp=m.fingerprint
        with self.assertRaises(ValueError):confirm(self.model,m,s,q,'entity:健太')
        self.assertEqual(m.fingerprint,fp)

    def test_invalid_answer_does_not_mutate(self):
        m=self.memory(True);s=self.session(m);q=assess(self.model,m,s)['questions'][0];fp=m.fingerprint
        with self.assertRaises(ValueError):confirm(self.model,m,s,q,'entity:未知')
        self.assertEqual(fp,m.fingerprint)

    def test_packet_tampering_invalidates_session(self):
        m=self.memory();s=self.session(m);s.packet['real'][0]+=0.001
        self.assertEqual(assess(self.model,m,s)['status'],'abstain')

    def test_intervening_memory_change_invalidates_session(self):
        m=self.memory();s=self.session(m);teach(self.model,m,SCOPE,self.packet,request(self.model,m,SCOPE,self.packet,A,'entity:由紀'))
        self.assertEqual(assess(self.model,m,s)['status'],'abstain')

    def test_unknown_scope_not_automatically_registered(self):
        m=self.memory();fp=m.fingerprint
        with self.assertRaises(ValueError):Session(self.model,m,{**SCOPE,'episode':'other'},self.packet)
        self.assertEqual(fp,m.fingerprint)

    def test_generation_and_assessment_are_read_only(self):
        m=self.memory();s=self.session(m,'missing');fp=m.fingerprint;p=copy.deepcopy(s.payload());generate(self.model,m,s)
        self.assertEqual(fp,m.fingerprint);self.assertEqual(p,s.payload())

    def test_session_round_trip_and_memory_reload(self):
        m=self.memory(True);s=self.answer_all(m,self.session(m,'old'))
        with tempfile.TemporaryDirectory(prefix='ssdoc05-unit-') as folder:
            d=Path(folder);m.save(d/'memory');s.save(d/'session.json');new=RevisionMemory.load(d/'memory',self.model.codec.candidates)
            resumed=Session.load(d/'session.json',self.model,new);self.assertEqual(generate(self.model,new,resumed)['text'],TEXT)
            self.assertEqual(generate(self.model,new,self.session(new,'missing'))['text'],TEXT)

    def test_receipts_store_revisions_not_answer_values(self):
        m=self.memory(True);s=self.answer_all(m,self.session(m));self.assertEqual(set(s.confirmed),{A,B})
        self.assertTrue(all(type(v) is int for v in s.confirmed.values()))

    def test_no_teacher_no_forced_generation(self):
        m=self.memory(True);r=generate(self.model,m,self.session(m,'old_partial'));self.assertNotIn('text',r)

    def test_wrong_formal_answer_not_truth_checked(self):
        m=self.memory();s=self.session(m,'old');q=assess(self.model,m,s)['questions'][0]
        new,_=confirm(self.model,m,s,q,'entity:花子');self.assertIn('花子が健太を',generate(self.model,m,new)['text'])

    def test_question_has_no_teacher_answer(self):
        m=self.memory(True);qs=assess(self.model,m,self.session(m))['questions']
        for q in qs:self.assertNotIn('value',q);self.assertNotIn('由紀',q['prompt'])

if __name__=='__main__':unittest.main()
