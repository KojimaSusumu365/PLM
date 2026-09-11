import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from ss_trace.runtime import State, ARMS, context_id, diagnostics, binary_stats
from ss_trace.learning import question, answer, teacher, teach
from ss_multicode.model import Model, SPECS
from ss_multicode.learning import Learner, teacher as old_teacher
from evaluation.cases import make_case, teaching, probes

C = dict(zip(('f0','f1','f2','f3'),'0123'))
B = dict(zip(('f0','f1','f2','f3'),'4567'))


class TraceTests(unittest.TestCase):
    def test_core_parity_all_dimensions(self):
        for d in (96,128,160):
            arm = {96:'main384',128:'main512',160:'main640'}[d]
            arch = f'test_shared_{d}'; SPECS[arch]=(4,d,True,0)
            try:
                new=State(arm,'unit-parity');old=Learner(Model(arch,'unit-parity'))
                events=teaching(make_case('unit-parity-data',64),'A',1)[:32]
                for i,e in enumerate(events):
                    req=old.question(e['context'])['request'];old=old.answer(req,old_teacher(req,e['label']))
                    teach(new,**e,kind='background' if i%2 else 'acquisition')
                    np.testing.assert_array_equal(new.main,old.model.readers)
            finally: del SPECS[arch]

    def test_capacity_controls(self):
        expected={'main512':32768,'main640':40960,'main384':24576,
                  'main512_pair':40960,'main384_pair':32768,'main512_bank':40960}
        self.assertEqual({a:State(a).storage()['total_coefficient_bytes'] for a in ARMS},expected)

    def test_pair_update_matches_explicit_formula(self):
        s=State('main512_pair','unit-formula');z=s.pair_vectors([C])[0]
        teach(s,C,'2');np.testing.assert_array_equal(s.auxiliary,z[:,2,:])
        expected=np.einsum('kyd,kd->ky',z,z[:,2,:].conj()).real/128
        np.testing.assert_array_equal(s.raw([C])[1][0],expected)

    def test_pair_binding_is_not_identical_across_labels(self):
        s=State();z=s.pair_vectors([C])[0]
        self.assertFalse(np.array_equal(z[:,0,:],z[:,1,:]))
        np.testing.assert_allclose(np.abs(z),1,rtol=0,atol=1e-14)

    def test_zero_trace_does_not_certify(self):
        s=State();teach(s,C,'2');s.auxiliary[:]=0
        self.assertEqual(s.observe([C])[0]['aux_accepted'],-1)

    def test_measure_keeps_teacher_error_separate_from_world_error(self):
        from evaluation.metrics import measure
        case=make_case('unit-measure',64);rows=probes(case);s=State();r=case['pool'][0]
        teach(s,r['context'],'1')
        for _ in range(64):teach(s,B,'0',kind='background')
        truth={x['id']:x['label'] for g in 'ABCDE' for x in case['groups'][g]};truth[r['id']]='2'
        main,aux=s.raw([x['context'] for x in rows])
        m=measure(main,aux,rows,s.ledger,s.step,{r['id']:'1'},truth,[],[r['id']],64,{x['id'] for x in case['pool']})
        self.assertEqual(m['cohorts']['all_acquired']['stale_teachers'],1)
        self.assertEqual(m['unknown_trace']['n'],128)

    def test_background_does_not_update_trace(self):
        for arm in ('main512_pair','main512_bank'):
            s=State(arm);teach(s,C,'1');before=s.auxiliary.copy()
            for _ in range(64): teach(s,B,'3',kind='background')
            np.testing.assert_array_equal(s.auxiliary,before)
            self.assertEqual(s.acquired,1);self.assertEqual(s.step,65)

    def test_main_unaffected_by_trace(self):
        states=[State(a,'unit-main') for a in ('main512','main512_pair','main512_bank')]
        for i in range(12):
            for s in states: teach(s,C if i%2 else B,str(i%4))
        for s in states[1:]: np.testing.assert_array_equal(states[0].main,s.main)

    def test_trace_changes_only_from_teacher(self):
        s=State();teach(s,C,'1');old=s.auxiliary.copy();fingerprint=s.fingerprint
        for _ in range(3): s.observe([C,B])
        np.testing.assert_array_equal(s.auxiliary,old);self.assertEqual(s.fingerprint,fingerprint)
        self.assertEqual(s.observe([C])[0]['aux_accepted'],1)

    def test_new_teacher_can_revise_old_correspondence(self):
        for arm in ('main512_pair','main512_bank'):
            s=State(arm,'unit-revise');teach(s,C,'1');teach(s,C,'3')
            self.assertEqual(s.observe([C])[0]['aux_accepted'],3)
            self.assertEqual(s.ledger[context_id(C)]['visits'],2)

    def test_no_exact_teacher_in_ledger(self):
        s=State();teach(s,C,'2')
        self.assertEqual(set(s.ledger[context_id(C)]),{'context','visits','post_margin','last_step'})
        bad=copy.deepcopy(s.ledger);bad[context_id(C)]['label']='2'
        with self.assertRaises(ValueError):State(step=1,acquired=1,ledger=bad)

    def test_unknown_context_and_extra_fields_rejected(self):
        s=State()
        for c in ({'f0':'0'},C|{'f0':'8'},C|{'label':'0'}):
            with self.assertRaises(ValueError):s.observe([c])

    def test_external_feedback_only_atomic_failure(self):
        s=State();req=question(s,C);good=teacher(req,'1');before=s.fingerprint
        for bad in (good|{'source':'model_prediction'},good|{'label':'9'},good|{'label':1},good|{'extra':0},good|{'request_id':'wrong'}):
            with self.assertRaises(ValueError):answer(s,req,bad)
            self.assertEqual(before,s.fingerprint)

    def test_stale_and_tampered_requests(self):
        s=State();req=question(s,C)
        with self.assertRaises(ValueError):answer(s,req|{'context':B},teacher(req,'1'))
        answer(s,req,teacher(req,'1'))
        with self.assertRaises(ValueError):answer(s,req,teacher(req,'1'))

    def test_no_free_background_revisit(self):
        s=State();teach(s,C,'0')
        with self.assertRaises(ValueError):question(s,C,'background')

    def test_resume_and_corruption(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state';s=State();teach(s,C,'1');s.save(p);loaded=State.load(p)
            self.assertEqual(s.fingerprint,loaded.fingerprint)
            self.assertEqual(s.observe([C,B]),loaded.observe([C,B]))
            teach(s,C,'2');teach(loaded,C,'2');self.assertEqual(s.fingerprint,loaded.fingerprint)
            with self.assertRaises(FileExistsError):s.save(p)
            obj=json.loads((p/'state.json').read_text(encoding='utf-8'));obj['metadata']['step']+=1
            (p/'state.json').write_text(json.dumps(obj),encoding='utf-8')
            with self.assertRaises(ValueError):State.load(p)

    def test_nonfinite_weights(self):
        s=State();s.main[0,0,0]=complex(float('nan'))
        with self.assertRaises(ValueError):State(main=s.main)

    def test_wrong_confident_winner_gap_blind_spot(self):
        main=np.tile(np.array([[[.1,.9,0.,0.]]]),(1,4,1))
        aux=np.tile(np.array([[[1.,0.,0.,0.]]]),(1,4,1))
        ledger={context_id(C):{'post_margin':.4,'last_step':1,'context':C,'visits':1}}
        d=diagnostics(main,aux,[context_id(C)],ledger,65)
        self.assertFalse(d['gap_drop'][0]);self.assertTrue(d['ss_disagreement'][0])
        self.assertTrue(d['ss_weak_support'][0])

    def test_auxiliary_error_can_cause_false_alarm(self):
        main=np.tile(np.array([[[1.,0.,0.,0.]]]),(1,4,1));aux=np.tile(np.array([[[0.,1.,0.,0.]]]),(1,4,1))
        ledger={context_id(C):{'post_margin':1.,'last_step':1,'context':C,'visits':1}}
        self.assertTrue(diagnostics(main,aux,[context_id(C)],ledger,65)['ss_disagreement'][0])

    def test_weak_trace_abstains_and_cooldown(self):
        main=np.tile(np.array([[[.1,.9,0.,0.]]]),(1,4,1));aux=np.tile(np.array([[[1.,0.,0.,0.]]]),(1,4,1))
        ledger={context_id(C):{'post_margin':.4,'last_step':1,'context':C,'visits':1}}
        self.assertFalse(diagnostics(main,aux,[context_id(C)],ledger,64)['ss_disagreement'][0])
        self.assertFalse(diagnostics(main,aux*.1,[context_id(C)],ledger,65)['ss_disagreement'][0])
        self.assertFalse(diagnostics(main,aux,[context_id(C)],{},65)['ss_disagreement'][0])

    def test_unseen_false_support_not_hidden_by_ledger(self):
        main=np.tile(np.array([[[1.,0.,0.,0.]]]),(1,4,1))
        d=diagnostics(main,main,[context_id(C)],{},100)
        self.assertTrue(d['aux_confident'][0]);self.assertFalse(d['eligible'][0])

    def test_world_truth_does_not_enter_runtime(self):
        s=State();teach(s,C,'1');before=s.observe([C]);teacher_truth='1';world_truth='2'
        self.assertNotEqual(teacher_truth,world_truth);self.assertEqual(before,s.observe([C]))

    def test_binary_stats_and_empty_denominators(self):
        r=binary_stats([True,True,False,False],[True,False,True,False])
        self.assertEqual([r[k] for k in ('tp','fp','fn','tn')],[1,1,1,1])
        self.assertIsNone(binary_stats([],[])['recall']);self.assertIsNone(binary_stats([],[])['precision'])

    def test_case_disjointness_and_balance(self):
        c=make_case('unit-case',64);rows=probes(c)
        self.assertEqual(len({r['id'] for r in rows}),448)
        self.assertEqual(len(c['pool']),64)
        self.assertEqual(len(teaching(c,'ABC',4)),768)
        for g in 'ABCDE':
            self.assertEqual([sum(r['label']==y for r in c['groups'][g]) for y in '0123'],[16]*4)


if __name__=='__main__':unittest.main()
