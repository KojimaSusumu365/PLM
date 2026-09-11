import copy
import inspect
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from plm_l1_v013.training import fit as old_fit
from ss_weighting.learning import coefficients, learn, RIDGE
from ss_weighting.memory import Memory, decide
from ss_weighting.training import fit, fit_structured
from evaluation.weight_cases import memory_case


def rows():
    return [{'context':{'a':str(a),'b':str(b),'c':str(c)},'label':str(a)}
            for a in (0,1) for b in (0,1) for c in (0,1) if (a,b,c)!=(1,1,1)]


class LearningTests(unittest.TestCase):
    def test_identity_kernel_all_methods(self):
        t=np.eye(4)
        for method in ('uniform','positive','residual'):
            b,a=coefficients(np.eye(4),t,method)
            np.testing.assert_allclose(b,t,atol=1e-12)
    def test_positive_bounds_and_no_cross_class(self):
        g=np.array([[1,.5,-.1],[.5,1,.2],[-.1,.2,1]])
        t=np.array([[1,0],[1,0],[0,1]])
        b,a=coefficients(g,t,'positive')
        self.assertTrue(np.all(b[t==0]==0))
        self.assertTrue(np.all((b[t==1]>=.25)&(b[t==1]<=2)))
        self.assertLessEqual(a['final_objective'],a['initial_objective']+1e-12)
    def test_residual_stationarity(self):
        g=np.array([[1,.6],[.6,1]])
        t=np.eye(2)
        b,a=coefficients(g,t,'residual')
        np.testing.assert_allclose(g.T@(g@b-t)+RIDGE*(b-t),0,atol=1e-12)
        self.assertLess(a['final_objective'],a['initial_objective'])
        self.assertGreater(a['negative_coefficients'],0)
    def test_singular_gram_regularized(self):
        b,a=coefficients(np.ones((4,4)),np.eye(4),'residual')
        self.assertTrue(np.isfinite(b).all())
    def test_gain_is_only_scaling(self):
        case=memory_case('unit',16)
        u,_=fit(case['teachers'],dimension=32)
        g,_=fit(case['teachers'],dimension=32,method='gain2')
        np.testing.assert_array_equal(g.weights/2,u.weights)
    def test_invalid_method(self):
        with self.assertRaises(ValueError): coefficients(np.eye(2),np.eye(2),'invalid')
    def test_invalid_gram(self):
        with self.assertRaises(ValueError): coefficients(np.array([[1,1],[0,1]]),np.eye(2),'positive')
    def test_invalid_targets(self):
        with self.assertRaises(ValueError): coefficients(np.eye(2),np.ones((2,2)),'positive')
    def test_nonfinite(self):
        with self.assertRaises(ValueError): learn(np.array([[np.nan],[1]]),np.eye(2),'positive')
    def test_response_orientation(self):
        rng=np.random.default_rng(7)
        b=np.exp(2j*np.pi*rng.random((8,32)))
        t=np.eye(2)[np.arange(8)%2]
        for method in ('positive','residual'):
            w,a=learn(b,t,method)
            beta,_=coefficients((b@b.conj().T).real/32,t,method)
            np.testing.assert_allclose((b@w.conj().T).real/32,((b@b.conj().T).real/32)@beta,atol=1e-12)


class RuntimeTests(unittest.TestCase):
    def test_duplicate_teachers_no_frequency_gain(self):
        r=memory_case('unit',16)['teachers']
        for method in ('uniform','positive','residual'):
            a,_=fit(r,method=method)
            b,_=fit(r+r[:4],method=method)
            np.testing.assert_array_equal(a.weights,b.weights)
            self.assertEqual(a.fingerprint,b.fingerprint)
    def test_conflicting_teacher_rejected(self):
        r=rows(); r.append({'context':r[0]['context'],'label':'1'})
        with self.assertRaises(ValueError): fit(r)
    def test_oracle_schema_rejected(self):
        r=rows(); r[0]=dict(r[0],oracle='1')
        with self.assertRaises(ValueError): fit(r)
    def test_only_observed_teachers_in_api(self):
        self.assertEqual(set(inspect.signature(fit).parameters),{'rows','dimension','seed','method','backend'})
    def test_ss_no_key_table(self):
        for method in ('uniform','positive','residual'):
            m,_=fit(rows(),method=method)
            self.assertEqual(m.metadata['entries'],{})
            self.assertNotIn('beta',m.metadata)
    def test_same_weight_bytes(self):
        ms=[fit(rows(),method=x)[0] for x in ('uniform','positive','residual')]
        self.assertEqual(len({m.weights.nbytes for m in ms}),1)
    def test_zero_abstains(self):
        m,_=fit(rows()); z=Memory(copy.deepcopy(m.metadata),np.zeros_like(m.weights))
        self.assertTrue(all(x['value'] is None for x in z.predict([r['context'] for r in rows()])))
    def test_multi_hit_not_argmax(self):
        self.assertIsNone(decide([[1,2]],['0','1'])[0]['value'])
    def test_threshold_boundary(self):
        self.assertEqual(decide([[.5,.49]],['0','1'])[0]['value'],'0')
    def test_all_below_threshold(self):
        self.assertIsNone(decide([[.49,-1]],['0','1'])[0]['value'])
    def test_exact_unknown_rejected(self):
        m,_=fit(rows(),backend='exact')
        self.assertIsNone(m.predict([dict(a='1',b='1',c='1')])[0]['value'])
    def test_exact_equivalence(self):
        ms=[fit(rows(),backend='exact',method=x)[0] for x in ('uniform','positive','residual')]
        ps=[m.predict([r['context'] for r in rows()]) for m in ms]
        self.assertEqual(ps[0],ps[1]); self.assertEqual(ps[1],ps[2])
    def test_invalid_context(self):
        m,_=fit(rows())
        with self.assertRaises(ValueError): m.predict([{'a':'0'}])
    def test_save_load(self):
        for method in ('uniform','positive','residual'):
            m,_=fit(rows(),method=method)
            with tempfile.TemporaryDirectory() as d:
                m.save(Path(d)/'m'); b=Memory.load(Path(d)/'m')
                self.assertEqual(b.fingerprint,m.fingerprint)
                np.testing.assert_array_equal(b.weights,m.weights)
    def test_save_does_not_overwrite(self):
        m,_=fit(rows())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError): m.save(d)
    def test_tampered_model_rejected(self):
        m,_=fit(rows())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m';m.save(p)
            np.savez(p/'weights.npz',weights=m.weights+1)
            with self.assertRaises(ValueError): Memory.load(p)
    def test_dimension_rejected(self):
        with self.assertRaises(ValueError): fit(rows(),dimension=0)


class StructuredTests(unittest.TestCase):
    def test_masks_unchanged(self):
        original=old_fit(rows())[0]
        for method in ('uniform','positive','residual'):
            m,_=fit_structured(rows(),method=method)
            self.assertEqual([x['mask'] for x in m.members],[x['mask'] for x in original.members])
    def test_uniform_weights_unchanged(self):
        a=old_fit(rows(),dimension=512,seed='unit')[0]
        b,_=fit_structured(rows(),dimension=512,seed='unit')
        for u,v in zip(a.members,b.members): np.testing.assert_array_equal(u['weights'],v['weights'])
    def test_unobserved_candidate_preserved(self):
        for method in ('uniform','positive','residual'):
            m,_=fit_structured(rows(),dimension=512,method=method)
            p=m.predict(dict(a='1',b='1',c='1'))
            self.assertIsNone(p['value']);self.assertTrue(p['learning_insufficient'])
    def test_true_input_ambiguity_not_voted_away(self):
        complete=rows()+[{'context':dict(a='1',b='1',c='1'),'label':'1'}]
        for method in ('uniform','positive','residual'):
            m,_=fit_structured(complete,method=method)
            self.assertEqual(m.predict({'b':'1','c':'1'})['reason'],'input_insufficient')
    def test_false_teacher_does_not_change_input_rows(self):
        r=rows();copy_r=copy.deepcopy(r)
        fit_structured(r,method='residual')
        self.assertEqual(r,copy_r)
    def test_no_session_integration_claim(self):
        m,_=fit_structured(rows(),method='positive')
        self.assertFalse(m.training['experimental_weighting']['online_teacher_session_integrated'])
        self.assertFalse(m.meta['eligible_for_inference'])


if __name__=='__main__': unittest.main()
