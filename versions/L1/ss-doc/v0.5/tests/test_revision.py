import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.contract import cell
from ss_revision.context import scope_key,address
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin,request,teach,prepare,learn
from ss_revision.runtime import complete,generate

TEXT='太郎が花子を助けた。その後、由紀が健太を褒めた。その後、健太が美咲を訪ねた。'
A='event:1/subject';B='event:1/object';SCOPE={'episode':'revision-unit','mutable':[A,B]}

class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=PartialModel.load(ROOT/'model');cls.known=cls.model.recover(read(cls.model,[TEXT])['packet'])['observation']
        cls.observation=copy.deepcopy(cls.known);cls.observation['cells'][A]=cell('ambiguous',['entity:由紀','entity:花子'])
        cls.packet=cls.model.encode(cls.observation)

    def state(self,method='versioned_pair'):
        m=RevisionMemory(self.model.codec.candidates,method,'revision-unit');begin(self.model,m,SCOPE,self.packet)
        p=self.packet
        for t,v,op in ((A,'entity:由紀','supply'),(B,'entity:次郎','revise'),(A,'entity:美咲','revise')):
            r=teach(self.model,m,SCOPE,p,request(self.model,m,SCOPE,p,t,v,op));p=r['packet']
        return m,p

    def missing(self,p,targets=(A,B)):
        o=copy.deepcopy(self.model.recover(p)['observation'])
        for t in targets:o['cells'][t]=cell('unobserved',[])
        return self.model.encode(o)

    def test_two_corrections_and_revision(self):
        for method in ('stable_overwrite','versioned_shared','versioned_pair','versioned_bank'):
            m,p=self.state(method);r=complete(self.model,m,SCOPE,self.missing(p))
            self.assertEqual(self.model.recover(r['packet'])['observation'],self.model.recover(p)['observation'])

    def test_legacy_context_reproduces_multi_hole_boundary(self):
        m,p=self.state('legacy_context');self.assertEqual(complete(self.model,m,SCOPE,self.missing(p))['status'],'needs_information')

    def test_second_correction_does_not_change_scope(self):
        m,p=self.state();self.assertEqual(scope_key(SCOPE,self.observation),scope_key(SCOPE,self.model.recover(p)['observation']))

    def test_nonmutable_change_changes_scope(self):
        o=copy.deepcopy(self.known);o['cells']['event:0/subject']=cell('known',['entity:次郎'])
        self.assertNotEqual(scope_key(SCOPE,o)[0],scope_key(SCOPE,self.known)[0])

    def test_different_episode_not_reused(self):
        m,p=self.state();self.assertEqual(complete(self.model,m,{**SCOPE,'episode':'other'},self.missing(p))['reason'],'unregistered_scope')

    def test_target_scope_changes_not_accepted(self):
        m,p=self.state();self.assertEqual(complete(self.model,m,{**SCOPE,'mutable':[A]},self.missing(p))['status'],'abstain')

    def test_versions_increment_per_target(self):
        m,p=self.state();self.assertEqual(next(iter(m.roots.values()))['versions'],{A:2,B:1})

    def test_saved_restart_with_two_missing_values(self):
        m,p=self.state()
        with tempfile.TemporaryDirectory(prefix='ssdoc04-test-') as t:
            m.save(Path(t)/'memory');new=RevisionMemory.load(Path(t)/'memory',self.model.codec.candidates)
            self.assertEqual(m.fingerprint,new.fingerprint)
            self.assertEqual(generate(self.model,m,SCOPE,self.missing(p)),generate(self.model,new,SCOPE,self.missing(p)))

    def test_reverse_generation(self):
        m,p=self.state();r=generate(self.model,m,SCOPE,self.missing(p),'reverse')
        self.assertEqual(r['text'],'健太が美咲を訪ねた。その前に、美咲が次郎を褒めた。その前に、太郎が花子を助けた。')

    def test_stale_confirmation_even_if_rebound_to_fresh_packet(self):
        m,p=self.state();msg=request(self.model,m,SCOPE,p,A,'entity:由紀','revise');msg.update(base_revision=0,revision=1);fp=m.fingerprint
        with self.assertRaisesRegex(ValueError,'stale_or_out_of_order'):teach(self.model,m,SCOPE,p,msg)
        self.assertEqual(fp,m.fingerprint)

    def test_future_confirmation_gap_rejected(self):
        m,p=self.state();msg=request(self.model,m,SCOPE,p,A,'entity:由紀','revise');msg['revision']+=1
        with self.assertRaisesRegex(ValueError,'stale_or_out_of_order'):teach(self.model,m,SCOPE,p,msg)

    def test_duplicate_prepared_teacher_rejected(self):
        m,p=self.state();msg=request(self.model,m,SCOPE,p,A,'entity:由紀','revise');t,_=prepare(self.model,m,SCOPE,p,msg);learn(m,t);fp=m.fingerprint
        with self.assertRaises(ValueError):learn(m,t)
        self.assertEqual(fp,m.fingerprint)

    def test_packet_hash_and_scope_are_bound(self):
        m,p=self.state();msg=request(self.model,m,SCOPE,p,A,'entity:由紀','revise')
        with self.assertRaises(ValueError):teach(self.model,m,SCOPE,self.missing(p),msg)
        with self.assertRaises(ValueError):teach(self.model,m,{**SCOPE,'episode':'other'},p,msg)

    def test_boolean_revision_not_integer(self):
        m,p=self.state();msg=request(self.model,m,SCOPE,p,B,'entity:健太','revise');msg['base_revision']=True
        with self.assertRaises(ValueError):teach(self.model,m,SCOPE,p,msg)

    def test_conflict_requires_explicit_resolution(self):
        m,p=self.state();o=self.model.recover(p)['observation'];o['cells'][A]=cell('conflict',['entity:美咲','entity:由紀']);q=self.model.encode(o);fp=m.fingerprint
        self.assertEqual(generate(self.model,m,SCOPE,q)['reason'],'explicit_conflict');self.assertEqual(fp,m.fingerprint)
        r=teach(self.model,m,SCOPE,q,request(self.model,m,SCOPE,q,A,'entity:由紀','resolve'))
        self.assertEqual(generate(self.model,m,SCOPE,self.missing(r['packet']))['status'],'generated')

    def test_ordinary_conflict_is_not_training(self):
        m,p=self.state();fp=m.fingerprint
        with self.assertRaises(ValueError):teach(self.model,m,SCOPE,p,request(self.model,m,SCOPE,p,A,'entity:由紀','supply'))
        self.assertEqual(fp,m.fingerprint)

    def test_explicit_old_value_not_overwritten(self):
        m,p=self.state();o=self.model.recover(p)['observation'];o['cells'][A]=cell('known',['entity:由紀']);q=self.model.encode(o);before=copy.deepcopy(q)
        self.assertEqual(generate(self.model,m,SCOPE,q)['reason'],'explicit_value_disagrees');self.assertEqual(before,q)

    def test_candidates_excluding_retained_answer_hold(self):
        m,p=self.state();o=self.model.recover(p)['observation'];o['cells'][A]=cell('ambiguous',['entity:花子','entity:由紀'])
        self.assertEqual(generate(self.model,m,SCOPE,self.model.encode(o))['reason'],'outside_current_candidates')

    def test_unconfirmed_second_target_holds(self):
        m=RevisionMemory(self.model.codec.candidates);begin(self.model,m,SCOPE,self.packet)
        r=teach(self.model,m,SCOPE,self.packet,request(self.model,m,SCOPE,self.packet,A,'entity:由紀'))
        self.assertEqual(generate(self.model,m,SCOPE,self.missing(r['packet']))['reason'],'unconfirmed_target')

    def test_no_partial_completion_when_one_target_lacks_support(self):
        m,p=self.state();q=self.missing(p);before=copy.deepcopy(q)
        for part in m.ss.parts.values():part.weights[:]=0
        r=complete(self.model,m,SCOPE,q);self.assertNotIn('packet',r);self.assertEqual(q,before)

    def test_inference_does_not_train_or_modify_source(self):
        m,p=self.state();q=self.missing(p);before=copy.deepcopy(q);fp=m.fingerprint;generate(self.model,m,SCOPE,q)
        self.assertEqual(q,before);self.assertEqual(m.fingerprint,fp)

    def test_metadata_has_only_target_versions_and_flags(self):
        m,p=self.state()
        for root,s in m.metadata()['roots'].items():
            self.assertEqual(len(root),64);self.assertEqual(set(s),{'versions','protect'})
            self.assertTrue(all(type(v) is int for v in s['versions'].values()))

    def test_zero_ss_weights_cannot_recover_answers_from_versions(self):
        m,p=self.state()
        for part in m.ss.parts.values():part.weights[:]=0
        self.assertEqual(generate(self.model,m,SCOPE,self.missing(p))['status'],'needs_information')

    def test_no_memory_baseline_holds(self):
        m,p=self.state('none');self.assertEqual(generate(self.model,m,SCOPE,self.missing(p))['status'],'needs_information')

    def test_versioned_addresses_differ_but_stable_does_not(self):
        root=scope_key(SCOPE,self.known)[0]
        self.assertNotEqual(address('versioned',root,A,1),address('versioned',root,A,2))
        self.assertEqual(address('stable',root,A,1),address('stable',root,A,2))

    def test_protection_policy_cannot_silently_change(self):
        m,p=self.state()
        with self.assertRaises(ValueError):begin(self.model,m,SCOPE,p,False)

    def test_equal_coefficient_capacity(self):
        for name in ('legacy_context','stable_overwrite','versioned_shared','versioned_pair','versioned_bank'):
            self.assertEqual(RevisionMemory(self.model.codec.candidates,name).cost()['total_coefficient_bytes'],94208)

    def test_wrong_but_valid_confirmation_is_not_truth_checked(self):
        m,p=self.state();r=teach(self.model,m,SCOPE,p,request(self.model,m,SCOPE,p,A,'entity:花子','revise'))
        self.assertIn('花子が次郎を',generate(self.model,m,SCOPE,self.missing(r['packet']))['text'])

    def test_changed_order_is_new_scope(self):
        o=copy.deepcopy(self.known);o['presentation']=o['presentation'][::-1]
        self.assertNotEqual(scope_key(SCOPE,self.known)[0],scope_key(SCOPE,o)[0])

    def test_invalid_scope_and_leaked_packet_rejected(self):
        m,p=self.state()
        for scope in ({**SCOPE,'mutable':[A,A]},{**SCOPE,'answer':'entity:美咲'}):self.assertEqual(generate(self.model,m,scope,p)['status'],'abstain')
        self.assertEqual(generate(self.model,m,SCOPE,{**p,'answer':'entity:美咲'})['status'],'abstain')

if __name__=='__main__':unittest.main()
