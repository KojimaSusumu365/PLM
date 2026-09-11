import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.update import request
from ss_partial.contract import cell,normalize
from ss_retention.context import key,domain
from ss_retention.memory import CorrectionMemory
from ss_retention.learning import prepare,learn,teach
from ss_retention.runtime import complete,generate

TEXT='太郎が花子を助けた。その後、由紀が健太を褒めた。その後、健太が美咲を訪ねた。'
ALTERNATIVE=TEXT.replace('由紀が健太','花子が健太')
TARGET='event:1/subject'

class RetentionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=PartialModel.load(ROOT/'model')
        cls.packet=read(cls.model,[TEXT,ALTERNATIVE])['packet']
        cls.observation=cls.model.recover(cls.packet)['observation']
        cls.teacher=request(cls.packet,TARGET,'entity:由紀')

    def memory(self,method='split_pair',episode='case-a'):
        m=CorrectionMemory(self.model.codec.candidates,method,'unit-code')
        result=teach(self.model,m,episode,self.packet,self.teacher)
        self.assertEqual(result['status'],'confirmed')
        return m

    def test_no_memory_stays_pending(self):
        m=self.memory('none');self.assertEqual(generate(self.model,m,'case-a',self.packet)['status'],'needs_information')

    def test_all_ss_methods_can_recall_one_correction(self):
        for method in ('shared736','shared1472','split_pair','split_bank'):
            self.assertEqual(generate(self.model,self.memory(method),'case-a',self.packet)['text'],TEXT)

    def test_fresh_missing_observation(self):
        m=self.memory()
        for state in ('unobserved','unreadable'):
            o=copy.deepcopy(self.observation);o['cells'][TARGET]=cell(state,[])
            self.assertEqual(generate(self.model,m,'case-a',self.model.encode(o))['text'],TEXT)

    def test_different_episode_same_text_not_reused(self):
        r=generate(self.model,self.memory(),'case-b',self.packet)
        self.assertEqual(r['reason'],'unregistered');self.assertNotIn('text',r)

    def test_anchor_other_actor_change_not_reused(self):
        m=self.memory();o=copy.deepcopy(self.observation);o['cells']['event:0/subject']=cell('known',['entity:次郎'])
        self.assertEqual(generate(self.model,m,'case-a',self.model.encode(o))['reason'],'unregistered')

    def test_target_value_not_in_key(self):
        o=copy.deepcopy(self.observation);o['cells'][TARGET]=cell('known',['entity:次郎'])
        self.assertEqual(key('case-a',o,TARGET),key('case-a',self.observation,TARGET))

    def test_count_order_and_target_in_key(self):
        o=copy.deepcopy(self.observation);o['presentation']=o['presentation'][::-1]
        self.assertNotEqual(key('case-a',o,TARGET),key('case-a',self.observation,TARGET))
        self.assertNotEqual(key('case-a',self.observation,'event:0/subject'),key('case-a',self.observation,TARGET))

    def test_outside_candidates_hold(self):
        o=copy.deepcopy(self.observation);o['cells'][TARGET]=cell('ambiguous',['entity:花子','entity:次郎'])
        self.assertEqual(generate(self.model,self.memory(),'case-a',self.model.encode(o))['reason'],'memory_outside_current_candidates')

    def test_explicit_conflict_not_resolved_by_memory(self):
        o=copy.deepcopy(self.observation);o['cells'][TARGET]['state']='conflict'
        self.assertEqual(generate(self.model,self.memory(),'case-a',self.model.encode(o))['reason'],'explicit_conflict')

    def test_new_explicit_information_not_overwritten(self):
        o=copy.deepcopy(self.observation);o['cells'][TARGET]=cell('known',['entity:花子']);p=self.model.encode(o);original=copy.deepcopy(p)
        r=generate(self.model,self.memory(),'case-a',p)
        self.assertEqual(r['reason'],'new_explicit_information_disagrees');self.assertEqual(p,original)

    def test_explicit_revision_learnable(self):
        m=self.memory();r=complete(self.model,m,'case-a',self.packet);p=r['packet']
        teach(self.model,m,'case-a',p,request(p,TARGET,'entity:花子','revise'))
        self.assertEqual(generate(self.model,m,'case-a',self.packet)['text'],ALTERNATIVE)

    def test_background_cannot_modify_protected_coefficients(self):
        m=self.memory();w=m.parts['protected'].weights.copy()
        t,_=prepare(self.model,'case-b',self.packet,self.teacher,False);learn(m,t)
        np.testing.assert_array_equal(m.parts['protected'].weights,w)
        self.assertEqual(m.parts['main'].updates,2);self.assertEqual(m.parts['protected'].updates,1)

    def test_equal_coefficient_capacity(self):
        costs={method:CorrectionMemory(self.model.codec.candidates,method).cost()['total_coefficient_bytes'] for method in ('shared736','shared1472','split_pair','split_bank')}
        self.assertEqual(costs['shared1472'],94208);self.assertEqual(costs['split_pair'],94208);self.assertEqual(costs['split_bank'],94208);self.assertEqual(costs['shared736'],47104)

    def test_save_restart_and_requery(self):
        m=self.memory()
        with tempfile.TemporaryDirectory(prefix='ssdoc03-unit-') as t:
            m.save(Path(t)/'memory');new=CorrectionMemory.load(Path(t)/'memory',self.model.codec.candidates)
            self.assertEqual(m.fingerprint,new.fingerprint)
            self.assertEqual(generate(self.model,new,'case-a',self.packet)['text'],TEXT)

    def test_metadata_has_no_learned_answer_table(self):
        meta=self.memory().metadata()
        for p in meta['parts'].values():
            self.assertEqual(set(p),{'kind','dimension','seed','registry','updates','weights_sha256'})
            self.assertTrue(all(len(k)==64 for k in p['registry']))

    def test_zero_weights_keeps_registry_but_loses_answer(self):
        m=self.memory()
        for p in m.parts.values():p.weights[:]=0
        self.assertEqual(generate(self.model,m,'case-a',self.packet)['reason'],'weak_support')

    def test_remove_registry_gates_even_valid_ss_support(self):
        m=self.memory();k=key('case-a',self.observation,TARGET)
        for p in m.parts.values():p.registry.clear()
        r=m.recall(k,'subject');self.assertEqual(r['status'],'unregistered');self.assertTrue(r['raw']['protected']['accepted_raw'])

    def test_generation_does_not_self_train(self):
        m=self.memory();fp=m.fingerprint;generate(self.model,m,'case-a',self.packet)
        self.assertEqual(m.fingerprint,fp)

    def test_source_packet_not_saved_or_modified(self):
        m=self.memory();p=copy.deepcopy(self.packet);complete(self.model,m,'case-a',p)
        self.assertEqual(p,self.packet)
        self.assertNotIn('packet',m.metadata());self.assertNotIn('text',m.metadata())

    def test_non_target_meaning_unchanged(self):
        r=complete(self.model,self.memory(),'case-a',self.packet);o=self.model.recover(r['packet'])['observation']
        self.assertTrue(all(v==o['cells'][k] for k,v in self.observation['cells'].items() if k!=TARGET))

    def test_reversed_output(self):
        r=generate(self.model,self.memory(),'case-a',self.packet,'reverse')
        self.assertEqual(r['text'],'健太が美咲を訪ねた。その前に、由紀が健太を褒めた。その前に、太郎が花子を助けた。')

    def test_unresolved_other_field_refuses_teacher(self):
        o=copy.deepcopy(self.observation);o['cells']['event:0/polarity']=cell('unobserved',[]);p=self.model.encode(o)
        with self.assertRaises(ValueError):prepare(self.model,'case-a',p,request(p,TARGET,'entity:由紀'))

    def test_stale_teacher_does_not_change_memory(self):
        m=self.memory();fp=m.fingerprint;r=complete(self.model,m,'case-a',self.packet)
        with self.assertRaises(ValueError):teach(self.model,m,'case-a',r['packet'],self.teacher)
        self.assertEqual(m.fingerprint,fp)

    def test_ordinary_conflicting_teacher_not_learned(self):
        m=self.memory();fp=m.fingerprint;p=complete(self.model,m,'case-a',self.packet)['packet']
        with self.assertRaises(ValueError):teach(self.model,m,'case-a',p,request(p,TARGET,'entity:花子'))
        self.assertEqual(m.fingerprint,fp)

    def test_unknown_value_rejected(self):
        m=self.memory();fp=m.fingerprint
        with self.assertRaises(ValueError):learn(m,{'key':'a'*64,'domain':'subject','value':'entity:未知','protect':True})
        self.assertEqual(m.fingerprint,fp)

    def test_bad_or_leaked_packet_rejected(self):
        m=self.memory()
        for p in (self.packet|{'answer':'entity:由紀'},self.packet|{'real':[0.]*8192,'imag':[0.]*8192}):
            self.assertEqual(generate(self.model,m,'case-a',p)['status'],'abstain')

    def test_empty_episode_rejected(self):
        self.assertEqual(generate(self.model,self.memory(),'',self.packet)['status'],'abstain')

    def test_cache_clear_does_not_erase_learning(self):
        m=self.memory()
        for p in m.parts.values():p.cache.clear()
        self.assertEqual(generate(self.model,m,'case-a',self.packet)['text'],TEXT)

    def test_independent_channel_votes_required(self):
        m=self.memory('shared736');part=m.parts['main'];part.weights[2:]=0
        self.assertIsNone(part.recall(key('case-a',self.observation,TARGET),'subject')['value'])

    def test_protected_main_disagreement_holds(self):
        m=self.memory();t,_=prepare(self.model,'case-a',self.packet,request(self.packet,TARGET,'entity:花子'),False)
        learn(m,t)
        self.assertEqual(generate(self.model,m,'case-a',self.packet)['reason'],'memory_disagreement')

    def test_wrong_confirmation_is_not_truth_checked(self):
        m=CorrectionMemory(self.model.codec.candidates)
        teach(self.model,m,'case-a',self.packet,request(self.packet,TARGET,'entity:花子'))
        self.assertEqual(generate(self.model,m,'case-a',self.packet)['text'],ALTERNATIVE)

    def test_primary_dataset_identity_and_scope(self):
        from evaluation.cases import dataset,scene_key
        a,b=dataset(100),dataset(101)
        self.assertEqual(len(a),280);self.assertEqual(sum(c['kind']=='focal' for c in a),24)
        self.assertFalse({scene_key(c['meaning']) for c in a}&{scene_key(c['meaning']) for c in b})
        self.assertEqual(len({c['episode'] for c in a+b}),560)
        self.assertTrue(any(c['target'].startswith('time/') and c['known']['count']==3 for c in a if c['kind']=='focal'))

if __name__=='__main__':unittest.main()
