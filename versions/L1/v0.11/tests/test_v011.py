import copy,itertools,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from plm_l1_v011.algebra import Book,terms,canonical
from plm_l1_v011.core import Model,observe
from plm_l1_v011.training import fit,calibrate
from plm_l1_v011.portability import compare
from evaluation.tasks import tasks,ambiguous,semantic_queries,allowed,make_task
from evaluation.metrics import measure,equal_count

def xor():
    return [{'context':{'a':str(a),'b':str(b)},'label':str(a^b)} for a,b in itertools.product((0,1),repeat=2)]

class AlgebraTests(unittest.TestCase):
    def test_deterministic_atoms(self):self.assertTrue(np.array_equal(Book(512,'x').atom('a','0'),Book(512,'x').atom('a','0')))
    def test_field_tag_matters(self):self.assertFalse(np.array_equal(Book(512,'x').atom('a','0'),Book(512,'x').atom('b','0')))
    def test_unit_atom(self):self.assertTrue(np.allclose(abs(Book(512,'x').atom('a','0')),1))
    def test_terms(self):
        self.assertEqual(len(terms('abcdef','hybrid3')),41);self.assertEqual(len(terms('abcdef','additive')),6);self.assertEqual(len(terms('abcdef','product')),1)
    def test_additive_is_sum(self):
        b=Book(512,'x');q,n=b.vector({'a':'0','b':'1'},['a','b'],'additive');self.assertEqual(n,2);self.assertTrue(np.allclose(q,(b.atom('a','0')+b.atom('b','1'))/np.sqrt(2)))
    def test_product_missing_field_has_no_term(self):self.assertEqual(Book(512,'x').vector({'a':'0'},['a','b'],'product')[1],0)
    def test_additive_missing_preserves_full_scale(self):
        b=Book(512,'x');q,n=b.vector({'a':'0'},['a','b'],'additive');self.assertEqual(n,1);self.assertTrue(np.allclose(q,b.atom('a','0')/np.sqrt(2)))
    def test_hybrid_missing_terms_only(self):self.assertEqual(Book(512,'x').vector({'a':'0','b':'1'},['a','b','c'],'hybrid3')[1],3)

class LearningTests(unittest.TestCase):
    def model(self,**kw):r=xor();return fit(r,r,**kw)[0]
    def test_exact_additive_xor_cannot_recover(self):self.assertTrue(all(self.model(backend='exact').predict(r['context'])['value'] is None for r in xor()))
    def test_ss_additive_xor_cannot_recover(self):self.assertTrue(all(self.model().predict(r['context'])['value'] is None for r in xor()))
    def test_exact_product_xor(self):
        m=self.model(backend='exact',representation='product');self.assertTrue(all(m.predict(r['context'])['value']==r['label'] for r in xor()))
    def test_exact_hybrid_xor(self):
        m=self.model(backend='exact',representation='hybrid3');self.assertTrue(all(m.predict(r['context'])['value']==r['label'] for r in xor()))
    def test_ss_hybrid_xor(self):
        m=self.model(representation='hybrid3');self.assertTrue(all(m.predict(r['context'])['value']==r['label'] for r in xor()))
    def test_off_selection_labels_do_not_change_model(self):
        r=xor();v=copy.deepcopy(r)
        for row in v:row['label']='changed'
        self.assertEqual(fit(r,r)[0].fingerprint,fit(r,v)[0].fingerprint)
    def test_validation_cannot_directly_change_weights(self):
        r=xor();m,_,_=fit(r,r,representation='product',selector='validation')
        v=copy.deepcopy(r)
        for row in v:row['label']='changed'
        b,_,_=fit(r,v,representation='product',selector='validation')
        self.assertTrue(np.array_equal(m.members[0]['weights'],b.members[0]['weights']))
    def test_no_teacher_oracle_fields(self):
        r=xor();r[0]['true_dependencies']=['a']
        with self.assertRaises(ValueError):fit(r,xor())
    def test_selector_axis(self):
        t=make_task('development','unary');m,_,_=fit(t['train'],t['selection'],backend='exact',selector='validation');self.assertEqual(len(m.members[0]['mask']),1)
    def test_correlated_candidates_kept(self):
        t=ambiguous('development',0);m,_,_=fit(t['train'],t['selection'],backend='exact',selector='validation');self.assertEqual(len(m.members),2)
    def test_correlated_candidates_disagree(self):
        t=ambiguous('development',0);m,_,_=fit(t['train'],t['selection'],backend='exact',selector='validation')
        self.assertTrue(all(m.predict(r['context'])['value'] is None for r in t['test']))
    def test_added_examples_resolve(self):
        t=ambiguous('development',0);m,_,_=fit(t['train']+t['added'],t['selection'],backend='exact',selector='validation')
        self.assertEqual(len(m.members),1);self.assertTrue(all(m.predict(r['context'])['value']==r['label'] for r in t['test']))
    def test_overflow_veto(self):
        r=[{'context':dict.fromkeys('abcdef',str(i)),'label':str(i)} for i in (0,1)];m,_,_=fit(r,r,backend='exact',selector='validation')
        self.assertEqual(len(m.members),4);self.assertFalse(m.training['supported']);self.assertIsNone(m.predict(r[0]['context'])['value'])
    def test_fixed_coefficient_budget(self):
        t=ambiguous('development',0);m,_,_=fit(t['train'],t['selection'],dimension=512,selector='validation',budget='fixed_total')
        self.assertEqual(len(m.members),2);self.assertEqual(sum(x['dimension'] for x in m.members),512)
    def test_zero_weights(self):
        m=self.model(representation='hybrid3',enabled=False);self.assertTrue(all(m.predict(r['context'])['value'] is None for r in xor()))
    def test_calibration_does_not_update_weights(self):
        m=self.model(representation='hybrid3');w=m.members[0]['weights'].copy();calibrate(m,xor());self.assertTrue(np.array_equal(w,m.members[0]['weights']))
    def test_gate_no_guarantee(self):
        m=self.model(representation='hybrid3');c=calibrate(m,xor());self.assertFalse(c['statistical_guarantee'])
    def test_unknown_validation_values_count_as_abstention(self):
        r=xor();v=copy.deepcopy(r)
        for row in v:row['context']['a']='unseen'
        m,a,_=fit(r,v,selector='validation',representation='hybrid3')
        self.assertNotIn('unseen',m.config['vocabulary']['a']);self.assertFalse(m.training['supported']);self.assertTrue(all(t['validation_loss']==.5 for t in a['trials']))
    def test_unknown_calibration_values_abstain(self):
        m=self.model(representation='hybrid3');r=xor()
        for row in r:row['context']['a']='unseen'
        c=calibrate(m,r);self.assertFalse(c['feasible']);self.assertEqual(m.threshold,1e6);self.assertNotIn('unseen',m.config['vocabulary']['a'])
    def test_role_whole_labels(self):
        t=make_task('development','roles');m,_,_=fit(t['train'],t['selection'],backend='exact',representation='hybrid3',selector='validation')
        self.assertTrue(all(m.predict(r['context'])['value']==r['label'] for r in t['test']))

class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.model=fit(xor(),xor(),representation='hybrid3')[0]
    def packet(self):return self.model.encode(xor()[0]['context'])
    def test_packet_no_context_or_labels(self):
        p=self.packet();self.assertEqual(set(p),{'schema','model_fingerprint','members','eligible_for_inference'});self.assertNotIn('context',canonical(p));self.assertNotIn('label',canonical(p))
    def test_packet_roundtrip(self):self.assertEqual(self.model.decode(self.packet())['value'],'0')
    def test_all_erased_abstains(self):self.assertIsNone(self.model.decode(observe(self.packet(),0.,'x'))['value'])
    def test_observation_mask_reproducible(self):self.assertEqual(observe(self.packet(),.5,'x'),observe(self.packet(),.5,'x'))
    def test_partial_numeric_not_missing_semantics(self):
        p=observe(self.packet(),.5,'x');self.assertEqual(p['members'][0]['available_terms'],3);self.assertEqual(sum(p['members'][0]['observed']),1024)
    def test_packet_fingerprint_strict(self):
        p=self.packet();p['model_fingerprint']='wrong'
        with self.assertRaises(ValueError):self.model.decode(p)
    def test_old_packet_after_calibration_rejected(self):
        m=fit(xor(),xor(),representation='hybrid3')[0];p=m.encode(xor()[0]['context']);calibrate(m,xor())
        with self.assertRaises(ValueError):m.decode(p)
    def test_extra_field_rejected(self):
        p=self.packet();p['raw_text']='secret'
        with self.assertRaises(ValueError):self.model.decode(p)
    def test_invalid_numbers(self):
        for bad in (float('nan'),float('inf'),True,'0'):
            p=self.packet();p['members'][0]['real'][0]=bad
            with self.assertRaises(ValueError):self.model.decode(p)
    def test_erased_nonzero_rejected(self):
        p=self.packet();p['members'][0]['observed'][0]=False
        with self.assertRaises(ValueError):self.model.decode(p)
    def test_unknown_values_rejected(self):
        with self.assertRaises(ValueError):self.model.predict({'a':'unknown'})
    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):self.model.predict({'z':'0'})
    def test_no_observed_fields_abstain(self):self.assertIsNone(self.model.predict({})['value'])
    def test_exact_numeric_boundary(self):
        m=fit(xor(),xor(),backend='exact')[0]
        with self.assertRaises(ValueError):m.encode({'a':'0'})
    def test_readonly_prediction(self):
        before=self.model.fingerprint;self.model.predict(xor()[0]['context']);self.assertEqual(before,self.model.fingerprint)
    def test_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model';self.model.save(p);m=Model.load(p);self.assertEqual(m.fingerprint,self.model.fingerprint);self.assertTrue(compare(m,self.model,[r['context'] for r in xor()])['functional_passed'])
    def test_inventory_strict(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model';self.model.save(p);(p/'extra').touch()
            with self.assertRaises(ValueError):Model.load(p)
    def test_fresh_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):self.model.save(d)
    def test_functional_ulp_not_strict_identity(self):
        m=copy.deepcopy(self.model);w=m.members[0]['weights'];w.real[0,0]=np.nextafter(w.real[0,0],np.inf);m.refresh()
        r=compare(self.model,m,[x['context'] for x in xor()]);self.assertTrue(r['functional_passed']);self.assertFalse(r['strict_fingerprint_equal'])
    def test_functional_large_change_rejected(self):
        m=copy.deepcopy(self.model);m.members[0]['weights'][0,0]+=.01;m.refresh()
        self.assertFalse(compare(self.model,m,[x['context'] for x in xor()])['functional_passed'])
    def test_invalid_mask_type(self):
        p=self.packet();p['members'][0]['observed'][0]=1
        with self.assertRaises(ValueError):self.model.decode(p)

class EvaluationTests(unittest.TestCase):
    def test_splits_disjoint(self):
        from evaluate import disjoint
        self.assertTrue(all(disjoint(t) for t in tasks('development')))
    def test_hidden_label_is_not_justification(self):
        m=measure(['yes'],[['yes','no']]);self.assertEqual(m['correct'],0);self.assertEqual(m['unsafe_confirmations'],1);self.assertEqual(m['compatible_but_unjustified'],1)
    def test_all_abstain_risk_undefined(self):self.assertIsNone(measure([None],[['0','1']])['selective_risk'])
    def test_semantic_queries_deduplicated(self):
        t=make_task('development','unary');q=semantic_queries(t);self.assertEqual(len(q),len({canonical(r['context']) for r in q}))
    def test_missing_nuisance_can_remain_identifiable(self):
        qs=semantic_queries(make_task('development','unary'));self.assertTrue(any(len(q['allowed'])==1 for q in qs));self.assertTrue(any(len(q['allowed'])>1 for q in qs))
    def test_zero_equal_count_not_win(self):
        r=[{'method':'a','predictions':[{'gated':None,'allowed':['0'],'query_id':'q'}]},{'method':'b','predictions':[{'gated':'0','allowed':['0'],'query_id':'q'}]}]
        self.assertEqual(equal_count(r)['status'],'no_positive_common_coverage')
    def test_unknown_not_identifiable(self):self.assertEqual(measure([None],[[]])['identifiable_requests'],0)
    def test_protocol_constants_match_runtime(self):
        from evaluation.tasks import ROOT
        from plm_l1_v011.core import MIN_MARGIN,MAX_CANDIDATES,MAX_SELECTION_LOSS
        p=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
        self.assertEqual((p['min_margin'],p['candidate_cap'],p['selection_loss_cap']),(MIN_MARGIN,MAX_CANDIDATES,MAX_SELECTION_LOSS))

if __name__=='__main__':unittest.main()
