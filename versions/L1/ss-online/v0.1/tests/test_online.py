import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from ss_online.algebra import canonical
from ss_online.model import Model,decisions
from ss_online.learning import Learner
from evaluation.cases import make_case,stream,validate
from evaluation.metrics import trace_metrics,probe_metrics


def context(i=0):return dict(zip(('f0','f1','f2','f3'),map(str,(i%8,(i//8)%8,(i//64)%8,(i//512)%8))))


def teach(s,c=None,label='0',source='external_teacher'):
    q=s.question(context() if c is None else c)['request']
    return s.answer(q,{'schema':'plm-ss-online-feedback-01','request_id':q['request_id'],'source':source,'label':label})


class UpdateTests(unittest.TestCase):
    def test_01_initial_has_no_answer(self):
        p=Learner.start().question(context())['prediction'];self.assertIsNone(p['tentative']);self.assertIsNone(p['accepted'])
    def test_02_delta_corrects_own_response(self):
        s=Learner.start();new,a=teach(s)
        np.testing.assert_allclose(new.model.scores([context()]),[[.5,0,0,0]],atol=1e-12)
        self.assertAlmostEqual(a['teacher_mse_after']/a['teacher_mse_before'],.25)
    def test_03_repeated_delta_converges(self):
        s=Learner.start()
        for _ in range(12):s,_=teach(s)
        self.assertEqual(s.model.predict([context()])[0]['accepted'],'0')
        self.assertAlmostEqual(s.model.scores([context()])[0,0],1-2**-12)
    def test_04_delta5_counts_and_response(self):
        s,a=teach(Learner.start('delta5'))
        self.assertEqual(a['updates_this_answer'],5)
        self.assertAlmostEqual(s.model.scores([context()])[0,0],1-2**-5)
    def test_05_new_feedback_supersedes_wrong_answer(self):
        s=Learner.start('delta5');s,_=teach(s,label='1');s,_=teach(s,label='0')
        self.assertEqual(s.model.predict([context()])[0]['accepted'],'0')
    def test_06_accumulation_is_not_error_correction(self):
        s=Learner.start('accumulate')
        for _ in range(3):s,_=teach(s)
        self.assertAlmostEqual(s.model.scores([context()])[0,0],3)
    def test_07_exact_preserves_other_keys(self):
        s=Learner.start('exact');s,_=teach(s,context(0),'0');s,_=teach(s,context(1),'1')
        self.assertEqual([p['accepted'] for p in s.model.predict([context(0),context(1)])],['0','1'])
    def test_08_exact_corrects_not_accumulates(self):
        s=Learner.start('exact');s,_=teach(s,label='1');s,_=teach(s,label='0')
        self.assertEqual(len(s.model.entries),1);self.assertEqual(s.model.predict([context()])[0]['accepted'],'0')
    def test_09_no_feedback_means_no_learning(self):
        s,_=teach(Learner.start());fp=s.fingerprint;w=s.model.weights.copy()
        for i in range(100):s.question(context(i))
        self.assertEqual(s.fingerprint,fp);np.testing.assert_array_equal(w,s.model.weights)
    def test_10_old_state_unchanged(self):
        s=Learner.start();fp=s.fingerprint;new,a=teach(s)
        self.assertEqual(s.fingerprint,fp);self.assertEqual(s.step,0);self.assertEqual(new.step,1);self.assertFalse(s.model.weights.any())
    def test_11_complex_update_orientation(self):
        s=Learner.start();b=s.model.vector(context());s.model.weights[:]=np.exp(1j*np.arange(128))[None,:];s.model.refresh();s.refresh()
        score=s.model.score_vector(b);new,_=teach(s)
        np.testing.assert_allclose(new.model.weights,s.model.weights+.5*(np.array([1,0,0,0])-score)[:,None]*b,atol=1e-12)
    def test_12_ss_saves_no_exact_key_table(self):
        for m in ('accumulate','delta','delta5','replay32'):
            s,_=teach(Learner.start(m));self.assertEqual(s.model.entries,{})
    def test_13_duplicate_feedback_still_counts_experience(self):
        s=Learner.start('exact');s,_=teach(s);fp=s.fingerprint;s,_=teach(s)
        self.assertEqual(s.step,2);self.assertNotEqual(fp,s.fingerprint)


class FeedbackTests(unittest.TestCase):
    def test_14_prediction_source_rejected(self):
        s=Learner.start()
        with self.assertRaisesRegex(ValueError,'prediction_is_not_teacher'):teach(s,source='model_prediction')
        self.assertEqual(s.step,0)
    def test_15_unknown_label_rejected(self):
        with self.assertRaisesRegex(ValueError,'scope_review'):teach(Learner.start(),label='new')
    def test_16_stale_request(self):
        s=Learner.start();r=s.question(context())['request'];new,_=teach(s)
        with self.assertRaisesRegex(ValueError,'stale_request'):new.answer(r,{})
    def test_17_tampered_request(self):
        s=Learner.start();r=s.question(context())['request'];r['context']=context(1)
        with self.assertRaisesRegex(ValueError,'tampered_request'):s.answer(r,{})
    def test_18_feedback_id_mismatch(self):
        s=Learner.start();r=s.question(context())['request']
        with self.assertRaisesRegex(ValueError,'mismatch'):s.answer(r,{'schema':'plm-ss-online-feedback-01','request_id':'bad','source':'external_teacher','label':'0'})
    def test_19_oracle_field_rejected(self):
        s=Learner.start();r=s.question(context())['request']
        with self.assertRaisesRegex(ValueError,'feedback_schema'):s.answer(r,{'schema':'plm-ss-online-feedback-01','request_id':r['request_id'],'source':'external_teacher','label':'0','truth':'0'})
    def test_20_prediction_envelope_not_request(self):
        s=Learner.start()
        with self.assertRaisesRegex(ValueError,'request_schema'):s.answer(s.question(context()),{})
    def test_21_incomplete_input_rejected(self):
        with self.assertRaises(ValueError):Learner.start().question({'f0':'0'})
    def test_22_unknown_value_rejected(self):
        c=context();c['f0']='8'
        with self.assertRaises(ValueError):Learner.start().question(c)


class ReplayTests(unittest.TestCase):
    def test_23_capacity_bounded(self):
        s=Learner.start('replay32')
        for i in range(80):s,_=teach(s,context(i),str(i%4))
        self.assertEqual(len(s.buffer),32)
    def test_24_initial_empty_buffer_cost(self):
        s,a=teach(Learner.start('replay32'));self.assertEqual(a['updates_this_answer'],1);self.assertEqual(a['replay_updates'],0)
        s,a=teach(s,context(1),'1');self.assertEqual(a['updates_this_answer'],5);self.assertEqual(a['replay_updates'],4)
    def test_25_nonreplay_has_no_buffer(self):
        for m in ('accumulate','delta','delta5','exact'):
            s,_=teach(Learner.start(m));self.assertFalse(s.buffer)
    def test_26_corrected_label_updates_same_key_buffer(self):
        s=Learner.start('replay32')
        for _ in range(3):s,_=teach(s,label='1')
        s,_=teach(s,label='0')
        self.assertTrue(all(r['label']=='0' for r in s.buffer))
    def test_27_deterministic_replay(self):
        a=Learner.start('replay32');b=Learner.start('replay32')
        for i in range(40):a,_=teach(a,context(i),str(i%4));b,_=teach(b,context(i),str(i%4))
        self.assertEqual(a.fingerprint,b.fingerprint);np.testing.assert_array_equal(a.model.weights,b.model.weights)
    def test_28_buffer_accounted_separately(self):
        s,_=teach(Learner.start('replay32'));storage=s.storage()
        self.assertGreater(storage['replay_utf8_bytes'],2);self.assertEqual(storage['weight_bytes'],4*128*16)


class PersistenceTests(unittest.TestCase):
    def test_29_model_roundtrip(self):
        s,_=teach(Learner.start())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model';s.model.save(p);m=Model.load(p);self.assertEqual(m.fingerprint,s.model.fingerprint)
    def test_30_learner_resume(self):
        s=Learner.start('replay32')
        for i in range(35):s,_=teach(s,context(i),str(i%4))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'learner';s.save(p);b=Learner.load(p)
            s,_=teach(s,context(60),'1');b,_=teach(b,context(60),'1');self.assertEqual(s.fingerprint,b.fingerprint)
    def test_31_tamper_detected(self):
        s,_=teach(Learner.start())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m';s.model.save(p);np.savez(p/'weights.npz',weights=s.model.weights+1)
            with self.assertRaises(ValueError):Model.load(p)
    def test_32_buffer_tamper_detected(self):
        s,_=teach(Learner.start('replay32'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s';s.save(p);obj=json.loads((p/'learner.json').read_text(encoding='utf-8'));obj['state']['buffer'][0]['label']='3'
            (p/'learner.json').write_text(json.dumps(obj),encoding='utf-8')
            with self.assertRaises(ValueError):Learner.load(p)
    def test_33_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError):Learner.start().save(d)
    def test_34_nonfinite_weight_rejected(self):
        s=Learner.start();w=s.model.weights.copy();w[0,0]=np.nan
        with self.assertRaises(ValueError):Model(s.model.config,w)
    def test_35_prediction_does_not_open_inference(self):
        s=Learner.start('delta5');s,_=teach(s);p=s.question(context())['prediction'];self.assertFalse(p['eligible_for_inference']);self.assertFalse(p['score_is_probability'])


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.case=make_case('unit-online')
    def test_36_disjoint_keys(self):self.assertTrue(validate(self.case))
    def test_37_exact_presentation_count(self):self.assertEqual(sum(len(b['events']) for b in stream(self.case,'clean')),896)
    def test_38_corrupt_only_first_eight(self):
        events=[e for b in stream(self.case,'noisy_first') for e in b['events']]
        self.assertEqual(sum(e['corrupted'] for e in events),8);self.assertTrue(all(not e['corrupted'] for e in events[64:]))
    def test_39_scenarios_same_context_order(self):
        a=[e['id'] for b in stream(self.case,'clean') for e in b['events']];b=[e['id'] for b in stream(self.case,'noisy_first') for e in b['events']];self.assertEqual(a,b)
    def test_40_drift_only_selected_keys(self):
        blocks=stream(self.case,'clean');ids={e['id'] for b in blocks if b['phase']=='drift' for e in b['events']}
        self.assertEqual(ids,set(self.case['changed_A_ids']));self.assertEqual(len(ids),16)
    def test_41_unseen_guess_not_registered_fact(self):
        rows=[{'id':'new'}];m=probe_metrics(np.array([[.7,0,0,0]]),rows,set(),{})
        self.assertEqual(m['unseen_false_accept'],1);self.assertEqual(m['known_requests'],0)
    def test_42_multiple_support_abstains(self):self.assertIsNone(decisions([[1,1,0,0]],list('0123'))[0]['accepted'])
    def test_43_tentative_can_exist_when_abstaining(self):
        p=decisions([[.3,.2,0,0]],list('0123'))[0];self.assertEqual(p['tentative'],'0');self.assertIsNone(p['accepted'])
    def test_44_uniform_add_and_delta_differ(self):
        a,_=teach(Learner.start('accumulate'));b,_=teach(Learner.start('delta'));self.assertFalse(np.array_equal(a.model.weights,b.model.weights))
    def test_45_zero_prediction_does_not_read_replay(self):
        s,_=teach(Learner.start('replay32'));z=Model(s.model.config)
        p=z.predict([context()])[0];self.assertIsNone(p['accepted']);self.assertIsNone(p['tentative'])
    def test_46_tentative_abstention_not_wrong(self):
        r={'id':'x','truth':'0','teacher_label':'0','before':{'tentative':None,'accepted':None},'after':{'tentative':'0','accepted':'0'},'seen_before':False,'previous_tentative_error':False,'updates':1,'replay_updates':0}
        m=trace_metrics([r]);self.assertEqual(m['before_tentative_abstained'],1);self.assertEqual(m.get('before_tentative_wrong',0),0)
    def test_47_teacher_can_be_wrong(self):
        s,a=teach(Learner.start('exact'),label='1')
        self.assertEqual(a['after']['accepted'],'1');self.assertEqual(a['teacher_mse_after'],0)
        s,a=teach(s,label='0');self.assertEqual(a['after']['accepted'],'0')
    def test_48_drift_not_counted_as_stable_forgetting(self):
        from evaluate import snapshot
        s=Learner.start('exact')
        for r in self.case['groups']['A']:s,_=teach(s,r['context'],r['label'])
        known={r['id'] for r in self.case['groups']['A']};truth={r['id']:r['label'] for group in self.case['groups'].values() for r in group}
        for key in self.case['changed_A_ids']:truth[key]=str((int(truth[key])+1)%4)
        snap,_=snapshot(s,self.case,known,truth,'drift',0,known,{})
        self.assertEqual(snap['forgetting']['anchor_correct_count'],48);self.assertEqual(snap['forgetting']['lost_anchor_correct'],0)
        changed=next(g['metrics'] for g in snap['groups'] if g['group']=='changed_A');self.assertEqual(changed['accepted_wrong'],16)
    def test_49_empty_anchor_is_not_perfect_retention(self):
        from evaluate import snapshot
        truth={r['id']:r['label'] for group in self.case['groups'].values() for r in group}
        snap,_=snapshot(Learner.start(),self.case,set(),truth,'B',4,set(),{})
        self.assertTrue(snap['forgetting']['anchor_defined']);self.assertEqual(snap['forgetting']['anchor_correct_count'],0)
    def test_50_nonreplay_state_has_no_teacher_contexts(self):
        s,_=teach(Learner.start('delta'));self.assertFalse(s.state['buffer']);self.assertNotIn('rows',s.state);self.assertNotIn('teachers',s.state)


if __name__=='__main__':unittest.main()
