import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from ss_multicode.model import Model, policy
from ss_multicode.learning import Learner, teacher
from ss_multicode.algebra import digest
from ss_active.selection import context_id, normalize_pool, diagnostics, select, STRATEGIES
from ss_active.session import Session, feedback
from evaluation.cases import make_case, validate, teaching, truth_map
from evaluation.metrics import counts, summarize, probe_context
from evaluate import teach_events

C = {'f0':'0','f1':'1','f2':'2','f3':'3'}
C2 = dict(C, f0='1')
C3 = dict(C, f0='2')
POOL = [{'id': context_id(c), 'context': c} for c in (C,C2,C3)]


def learner(): return Learner(Model('concat512', 'unit'))


class SelectionTests(unittest.TestCase):
    def test01_ids_context_only(self): self.assertEqual(context_id(C), context_id(dict(reversed(list(C.items())))))
    def test02_pool_order_invariant(self):
        for strategy in STRATEGIES: self.assertEqual(select(learner().model, POOL, strategy), select(learner().model, list(reversed(POOL)), strategy))
    def test03_reject_labels(self):
        for key in ('label','truth','oracle','confidence'):
            with self.assertRaises(ValueError): normalize_pool([dict(POOL[0], **{key:'0'})])
    def test04_reject_wrong_id(self):
        with self.assertRaises(ValueError): normalize_pool([dict(POOL[0], id='label-0')])
    def test05_reject_duplicate(self):
        with self.assertRaises(ValueError): normalize_pool([POOL[0],POOL[0]])
    def test06_reject_bad_context(self):
        with self.assertRaises(ValueError): context_id(dict(C, f1=1))
    def test07_reject_empty_selection(self):
        with self.assertRaises(ValueError): select(learner().model, [])
    def test08_reject_wrong_architecture(self):
        with self.assertRaises(ValueError): select(Model('multi4'), POOL)
    def test09_zero_tied_votes(self):
        d = diagnostics(np.zeros((1,4,4))); self.assertEqual(d['gini'][0], .75); self.assertTrue((d['bank_choices'] == -1).all())
    def test10_unanimous_votes(self):
        r = np.zeros((1,4,4)); r[:,:,0] = 1; self.assertEqual(diagnostics(r)['gini'][0], 0)
    def test11_four_distinct_votes(self): self.assertEqual(diagnostics(np.eye(4)[None,:,:])['gini'][0], .75)
    def test12_three_one_split(self):
        r = np.eye(4)[[0,0,0,1]][None,:,:]; self.assertEqual(diagnostics(r)['gini'][0], .375)
    def test13_random_ignores_scores(self):
        m = learner().model; a = select(m, POOL, 'random')['selected_id']; m.readers += 3; m.refresh()
        self.assertEqual(a, select(m, POOL, 'random')['selected_id'])
    def test14_scoring_cost(self):
        m = learner().model
        self.assertEqual(select(m, POOL, 'random')['diagnostics']['contexts_scored_this_call'], 1)
        for st in ('ambiguity','disagreement'): self.assertEqual(select(m, POOL, st)['diagnostics']['contexts_scored_this_call'],3)
    def test15_selection_not_learning(self):
        m = learner().model; before = m.fingerprint
        for st in STRATEGIES: select(m, POOL, st)
        self.assertEqual(before,m.fingerprint); self.assertTrue((m.readers==0).all())
    def test16_votes_not_probability_claim(self): self.assertFalse(select(learner().model, POOL)['diagnostics']['score_is_probability'])
    def test17_ambiguity_ranking(self):
        m = learner().model; wanted = POOL[1]['id']
        def raw(cs):
            a = np.zeros((len(cs),4,4))
            for i,c in enumerate(cs): a[i,:,0] = .51 if context_id(c)==wanted else 1.; a[i,:,1] = .5
            return {'readers':a,'checker':np.empty((len(cs),0))}
        m.raw=raw; self.assertEqual(select(m,POOL,'ambiguity')['selected_id'], wanted)
    def test18_disagreement_ranking(self):
        m = learner().model; wanted=POOL[2]['id']
        def raw(cs):
            a=np.zeros((len(cs),4,4))
            for i,c in enumerate(cs): a[i] = np.eye(4) if context_id(c)==wanted else np.eye(4)[[0,0,0,0]]
            return {'readers':a,'checker':np.empty((len(cs),0))}
        m.raw=raw; self.assertEqual(select(m,POOL,'disagreement')['selected_id'], wanted)
    def test19_equal_priority_same_hash_tie(self):
        m=learner().model; answers=[select(m,POOL,st)['selected_id'] for st in STRATEGIES]; self.assertEqual(len(set(answers)),1)
    def test20_invalid_parameters(self):
        for kw in ({'strategy':'oracle'}, {'seed':''}, {'index':-1}):
            with self.assertRaises(ValueError): select(learner().model,POOL,**kw)
    def test21_invalid_scores(self):
        with self.assertRaises(ValueError): diagnostics(np.ones((1,3,4)))
        with self.assertRaises(ValueError): diagnostics(np.full((1,4,4),np.nan))


class SessionTests(unittest.TestCase):
    def setUp(self): self.s=Session(learner(),POOL,'ambiguity','unit'); self.req=self.s.ask(); self.fb=feedback(self.req,'0')
    def test22_single_teacher(self):
        new=self.s.answer(self.req,self.fb); self.assertEqual(new.learner.step,1); self.assertEqual(len(new.pool),2); self.assertEqual(len(new.acquired),1)
    def test23_prior_state_unchanged(self):
        fp=self.s.fingerprint; self.s.answer(self.req,self.fb); self.assertEqual(fp,self.s.fingerprint); self.assertEqual(len(self.s.pool),3)
    def test24_stale_request(self):
        new=self.s.answer(self.req,self.fb)
        with self.assertRaises(ValueError): new.answer(self.req,self.fb)
    def test25_tampered_request(self):
        q=copy.deepcopy(self.req); q['selection']['context']['f0']='7'
        with self.assertRaises(ValueError): self.s.answer(q,self.fb)
    def test26_unselected_candidate_rejected(self):
        q=copy.deepcopy(self.req); q['selection']['selected_id']='0'*64
        with self.assertRaises(ValueError): self.s.answer(q,self.fb)
    def test27_prediction_not_teacher(self):
        with self.assertRaises(ValueError): self.s.answer(self.req,dict(self.fb,source='model_prediction'))
    def test28_extra_truth_rejected(self):
        with self.assertRaises(ValueError): self.s.answer(self.req,dict(self.fb,truth='0'))
    def test29_unknown_label_rejected(self):
        with self.assertRaises(ValueError): self.s.answer(self.req,dict(self.fb,label='4'))
    def test30_request_id_rejected(self):
        with self.assertRaises(ValueError): self.s.answer(self.req,dict(self.fb,request_id='wrong'))
    def test31_no_repeat_and_exhaustion(self):
        s=self.s
        for _ in range(3): q=s.ask(); s=s.answer(q,feedback(q,'0'))
        self.assertEqual(len(set(s.acquired)),3)
        with self.assertRaises(ValueError): s.ask()
    def test32_no_teacher_table_or_replay(self):
        new=self.s.answer(self.req,self.fb)
        self.assertFalse(new.learner.model.entries)
        self.assertNotIn('label', json.dumps(new.state)); self.assertNotIn('buffer',new.state)
    def test33_new_label_not_authenticated_truth(self):
        new=self.s.answer(self.req,feedback(self.req,'3')); self.assertEqual(new.learner.step,1)
    def test34_invalid_acquired_ledger(self):
        with self.assertRaises(ValueError): Session(learner(),POOL,acquired={})
    def test35_save_load(self):
        s=self.s.answer(self.req,self.fb)
        with tempfile.TemporaryDirectory(prefix='actest-') as temp:
            p=Path(temp)/'s'; s.save(p); new=Session.load(p)
            self.assertEqual(new.fingerprint,s.fingerprint); self.assertEqual(new.ask(),s.ask())
            with self.assertRaises(FileExistsError): s.save(p)
    def test36_corrupt_state(self):
        with tempfile.TemporaryDirectory(prefix='actest-') as temp:
            p=Path(temp)/'s'; self.s.save(p); f=p/'session.json'; obj=json.loads(f.read_text()); obj['state']['seed']='changed'; f.write_text(json.dumps(obj))
            with self.assertRaises(ValueError): Session.load(p)
    def test37_same_base_different_strategies(self):
        other=Session(self.s.learner,POOL,'random','unit'); self.assertEqual(other.learner.fingerprint,self.s.learner.fingerprint)
    def test38_challenge_does_not_change_source(self):
        fp=self.s.learner.fingerprint; n=teach_events(self.s.learner,[{'context':C2,'label':'2'}]); self.assertEqual(fp,self.s.learner.fingerprint); self.assertEqual(n.step,1)
    def test39_shared_residual_flat_equivalence(self):
        s=learner(); flat=np.zeros((4,512),complex)
        for c,y in [(C,'0'),(C2,'1'),(C3,'2')]*3:
            b,_=s.model.vectors([c]); v=b[0].reshape(-1); target=np.array([int(str(i)==y) for i in range(4)])
            flat += .5*(target-(flat.conj()@v).real/512)[:,None]*v[None,:]
            s=teach_events(s,[{'context':c,'label':y}])
        np.testing.assert_allclose(flat,s.model.readers.transpose(1,0,2).reshape(4,512),atol=3e-15,rtol=0)


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.case=make_case('unit-data',64)
    def test40_data_validation(self): self.assertTrue(validate(self.case)); self.assertEqual(len(self.case['pool']),64)
    def test41_all_unseen_outside_pool(self):
        ids={r['id'] for r in self.case['pool']}; self.assertFalse(ids & {context_id(c) for c in self.case['unknown']})
        self.assertFalse(ids & {r['id'] for r in self.case['groups']['D']})
    def test42_teaching_counts(self): self.assertEqual(len(teaching(self.case,'ABC',4)),768); self.assertEqual(len(teaching(self.case,'D',2)),128)
    def test43_world_changes_only16_pool_labels(self):
        a=truth_map(self.case,'stationary'); b=truth_map(self.case,'changed_pool16'); self.assertEqual(sum(a[k]!=b[k] for k in a),16)
    def test44_two_worlds_same_first_request(self):
        s=Session(learner(),self.case['pool'],'disagreement','unit'); before=s.ask(); truth_map(self.case,'changed_pool16'); self.assertEqual(before,s.ask())
    def test45_known_unseen_counts(self):
        scores=np.zeros((3,4,4)); scores[:2,:,0]=1
        m=counts(scores,np.array([True,False,True]),[0,-1,1]); self.assertEqual(m['accepted_correct'],1); self.assertEqual(m['unseen_false_accept'],1); self.assertEqual(m['accepted_abstained'],1)
    def test46_recovery_then_relapse(self):
        rows=probe_context(self.case); n=len(rows); truth=truth_map(self.case,'stationary'); key=self.case['pool'][0]['id']; ix=next(i for i,r in enumerate(rows) if r['id']==key); y=int(truth[key]); old=(y+1)%4
        base=np.zeros((n,4,4)); base[ix,:,old]=1; pre=base.copy(); pre[ix]=0; pre[ix,:,y]=1
        m=summarize(base,self.case,'stationary',[key],True,base,pre,[key])
        self.assertEqual(m['correction_recurrence']['again_wrong'],1)
        self.assertEqual(m['groups']['pool_selected']['transitions']['tentative_recovery_lost_after_challenge'],1)
    def test47_empty_changed_group_not_success_rate(self):
        n=len(probe_context(self.case)); z=np.zeros((n,4,4)); m=summarize(z,self.case,'stationary',[],False,z,z,[])
        self.assertEqual(m['groups']['changed_pool']['requests'],0)
    def test48_coefficient_budget(self): self.assertEqual(learner().storage()['coefficient_bytes'],32768)
    def test49_data_reproducibility(self): self.assertEqual(self.case,make_case('unit-data',64))
    def test50_invalid_scenario(self):
        with self.assertRaises(ValueError): truth_map(self.case,'oracle')


if __name__=='__main__': unittest.main()
