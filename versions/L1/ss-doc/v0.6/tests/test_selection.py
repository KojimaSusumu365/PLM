import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.contract import cell
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin,request,teach
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate
from ss_select.features import NAMES,validate
from ss_select.memory import SelectorMemory
from ss_select.training import fit,update
from ss_select.runtime import Workset,candidates,choose
from ss_select.feedback import answer

TEXT='太郎が花子を助けた。その後、由紀が健太を褒めた。';A='event:1/subject';B='event:1/object'

class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=PartialModel.load(ROOT/'model');cls.packet=read(cls.model,[TEXT])['packet'];cls.scope={'episode':'selector-unit','mutable':[A,B]}

    def setup_case(self,weak=False):
        m=RevisionMemory(self.model.codec.candidates,'versioned_pair','selector-unit');begin(self.model,m,self.scope,self.packet)
        for t,v in ((A,'entity:由紀'),(B,'entity:健太')):teach(self.model,m,self.scope,self.packet,request(self.model,m,self.scope,self.packet,t,v))
        if weak:
            for part in m.ss.parts.values():part.weights[:]=0
        o=copy.deepcopy(self.model.recover(self.packet)['observation'])
        for t in (A,B):o['cells'][t]=cell('unobserved',[])
        return m,Workset(self.model,[{'id':'q','scope':self.scope,'packet':self.model.encode(o)}])

    def selector(self):
        s=SelectorMemory();x={n:0. for n in NAMES};x['bias']=1.;update(s,x,0.5);return s

    def test_feature_inventory_and_no_identifiers(self):
        m,w=self.setup_case();rows=candidates(m,w)
        self.assertEqual(set(rows[0]['features']),set(NAMES));self.assertTrue(all(type(v) is float for v in rows[0]['features'].values()))
        self.assertNotIn('q',rows[0]['features']);self.assertNotIn('value',rows[0]['question'])

    def test_features_invariant_to_query_identifier(self):
        m,w=self.setup_case();e=copy.deepcopy(w.entries);e[0]['id']='renamed';other=Workset(self.model,e)
        self.assertEqual([r['features'] for r in candidates(m,w)],[r['features'] for r in candidates(m,other)])

    def test_unknown_feature_refused(self):
        x={n:0. for n in NAMES};x['truth']=1.
        with self.assertRaises(ValueError):validate(x)

    def test_nonfinite_feature_refused(self):
        x={n:0. for n in NAMES};x['score']=float('nan')
        with self.assertRaises(ValueError):validate(x)

    def test_ss_learning_changes_predictions(self):
        s=SelectorMemory();x={n:0. for n in NAMES};x['bias']=1.;y=dict(x);y['supported']=1.
        examples=[{'features':x,'reward':1.},{'features':y,'reward':0.}]*32
        fit(s,examples);self.assertGreater(s.predict(x),s.predict(y)+0.25)

    def test_zero_coefficients_remove_learned_value(self):
        s=self.selector();x={n:0. for n in NAMES};x['bias']=1.;self.assertGreater(s.predict(x),0)
        s.weights[:]=0;self.assertEqual(s.predict(x),0)

    def test_inference_does_not_change_memories_or_input(self):
        m,w=self.setup_case();s=self.selector();before=(m.fingerprint,s.fingerprint,copy.deepcopy(w.entries))
        choose(m,w,selector=s);self.assertEqual((m.fingerprint,s.fingerprint,w.entries),before)

    def test_untrained_selector_refused(self):
        m,w=self.setup_case()
        with self.assertRaises(ValueError):choose(m,w,selector=SelectorMemory())

    def test_random_is_reproducible(self):
        m,w=self.setup_case();self.assertEqual(choose(m,w,'random'),choose(m,w,'random'))

    def test_rule_allows_explicit_optional_maintenance(self):
        m,w=self.setup_case();r=choose(m,w,'rule');self.assertFalse(r['question']['required_now']);self.assertEqual(r['priority'],0)

    def test_weak_memory_requests_required_confirmation(self):
        m,w=self.setup_case(True);self.assertTrue(choose(m,w,'rule')['question']['required_now'])

    def test_excluded_target_is_not_selected_twice(self):
        m,w=self.setup_case();q=choose(m,w,'rule')['question'];r=choose(m,w,'rule',excluded=[['q',q['target']]])
        self.assertNotEqual(r['question']['target'],q['target'])

    def test_budget_exhausted_candidates_refused(self):
        m,w=self.setup_case()
        with self.assertRaises(ValueError):choose(m,w,'rule',excluded=[['q',A],['q',B]])

    def test_confirmation_changes_only_content_memory(self):
        m,w=self.setup_case();s=self.selector();fp=s.fingerprint;before=copy.deepcopy(w.entries);q=choose(m,w,selector=s)['question']
        r=answer(self.model,m,w,q,'entity:由紀' if q['target']==A else 'entity:健太')
        self.assertTrue(r['local_audit']['other_cells_unchanged']);self.assertEqual(s.fingerprint,fp);self.assertEqual(w.entries,before)
        self.assertTrue(r['confirmed_packet_discarded'])

    def test_stale_question_refused(self):
        m,w=self.setup_case();q=choose(m,w,'rule')['question'];v='entity:由紀' if q['target']==A else 'entity:健太'
        answer(self.model,m,w,q,v);fp=m.fingerprint
        with self.assertRaises(ValueError):answer(self.model,m,w,q,v)
        self.assertEqual(fp,m.fingerprint)

    def test_invalid_external_value_has_no_update(self):
        m,w=self.setup_case();q=choose(m,w,'rule')['question'];fp=m.fingerprint
        with self.assertRaises(ValueError):answer(self.model,m,w,q,'entity:未知')
        self.assertEqual(fp,m.fingerprint)

    def test_wrong_but_valid_teacher_can_be_learned(self):
        m,w=self.setup_case();q=next(r['question'] for r in candidates(m,w) if r['question']['target']==A)
        answer(self.model,m,w,q,'entity:花子');e=w.entries[0];g=generate(self.model,m,Session(self.model,m,e['scope'],e['packet']))
        self.assertIn('花子が健太を',g['text'])

    def test_two_answers_then_fresh_ss_only_generation(self):
        m,w=self.setup_case(True);history=[]
        for _ in range(2):
            q=choose(m,w,'rule',excluded=history)['question'];answer(self.model,m,w,q,'entity:由紀' if q['target']==A else 'entity:健太',history);history.append(['q',q['target']])
        e=w.entries[0];s=Session(self.model,m,e['scope'],e['packet']);self.assertEqual(s.confirmed,{})
        self.assertEqual(generate(self.model,m,s)['text'],TEXT)

    def test_supported_rank_does_not_bypass_generation_gate(self):
        m,w=self.setup_case(True);s=self.selector();choose(m,w,selector=s);e=w.entries[0]
        self.assertEqual(generate(self.model,m,Session(self.model,m,e['scope'],e['packet']))['status'],'needs_confirmation')

    def test_workset_mutation_refused(self):
        m,w=self.setup_case();w.entries[0]['id']='changed'
        with self.assertRaises(ValueError):choose(m,w,'rule')

    def test_workset_requires_two_missing_targets(self):
        with self.assertRaises(ValueError):Workset(self.model,[{'id':'q','scope':self.scope,'packet':self.packet}])

    def test_duplicate_workset_entry_refused(self):
        _,w=self.setup_case()
        with self.assertRaises(ValueError):Workset(self.model,w.entries*2)

    def test_selector_save_reload_and_tamper(self):
        s=self.selector()
        with tempfile.TemporaryDirectory(prefix='ssdoc06-unit-') as d:
            s.save(Path(d)/'model');loaded=SelectorMemory.load(Path(d)/'model');self.assertEqual(s.fingerprint,loaded.fingerprint)
            with np.load(Path(d)/'model/weights.npz',allow_pickle=False) as z:np.testing.assert_array_equal(s.weights,z['weights'])

    def test_selector_capacity_fixed(self):self.assertEqual(SelectorMemory().cost()['coefficient_bytes'],16384)

    def test_tampered_selector_coefficients_refused(self):
        s=self.selector()
        with tempfile.TemporaryDirectory(prefix='ssdoc06-tamper-') as d:
            folder=Path(d)/'model';s.save(folder);w=s.weights.copy();w[0,0]+=1.;np.savez_compressed(folder/'weights.npz',weights=w)
            with self.assertRaises(ValueError):SelectorMemory.load(folder)

    def test_teacher_field_cannot_enter_workset(self):
        _,w=self.setup_case();e=copy.deepcopy(w.entries);e[0]['truth']='hidden'
        with self.assertRaises(ValueError):Workset(self.model,e)

    def test_unknown_scope_not_automatically_registered(self):
        m,w=self.setup_case();e=copy.deepcopy(w.entries);e[0]['scope']['episode']='other';other=Workset(self.model,e);fp=m.fingerprint
        with self.assertRaises(ValueError):choose(m,other,'rule')
        self.assertEqual(fp,m.fingerprint)

    def test_question_cannot_be_rebound_to_another_target(self):
        m,w=self.setup_case();q=choose(m,w,'rule')['question'];q['root']='0'*64;fp=m.fingerprint
        with self.assertRaises(ValueError):answer(self.model,m,w,q,'entity:由紀')
        self.assertEqual(fp,m.fingerprint)

    def test_counterfactual_internal_update_matches_public_answer(self):
        from evaluation.delay_experiment import branch_confirmation
        m,w=self.setup_case();other=copy.deepcopy(m);q=choose(m,w,'rule')['question'];value='entity:由紀' if q['target']==A else 'entity:健太'
        record={'root':q['root'],'teachers':[{'prepared':{'legacy_key':'0'*64}}]}
        branch_confirmation(other,record,q['target'],value);answer(self.model,m,w,q,value)
        self.assertEqual(m.fingerprint,other.fingerprint)

    def test_cold_generation_cannot_use_confirmation_receipts(self):
        m,w=self.setup_case();q=choose(m,w,'rule')['question'];answer(self.model,m,w,q,'entity:由紀' if q['target']==A else 'entity:健太')
        for part in m.ss.parts.values():part.weights[:]=0
        e=w.entries[0];s=Session(self.model,m,e['scope'],e['packet']);self.assertEqual(s.confirmed,{})
        self.assertEqual(generate(self.model,m,s)['status'],'needs_confirmation')

if __name__=='__main__':unittest.main()
