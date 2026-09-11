import copy,json,tempfile,unittest
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_multicode.model import Model
from ss_multicode.learning import Learner,teacher
from ss_active.selection import select,normalize_state,validate_config,context_id,STRATEGIES
from ss_active.base_selection import normalize_pool,select as old_select
from ss_active.session import Session,feedback
from evaluation.cases import make_case,validate,teaching,truth_map
from evaluation.metrics import summarize,probes,decisions
from evaluation.choose_config import choose
from evaluate import teach_events,run

CFG={'explore_every':4,'revisit_every':4,'cooldown':64,'drop_margin':.05,'max_visits':2}
CONTEXTS=[dict(zip(('f0','f1','f2','f3'),map(str,(i,1,2,3)))) for i in range(6)]
POOL=normalize_pool([{'id':context_id(c),'context':c} for c in CONTEXTS])


def learner():return Learner(Model('concat512','unit2'))
def state(strategy='ambiguity_once',ledger=None,step=0):return {'schema':'plm-ss-active2-selection-state','pool':POOL,'ledger':{} if ledger is None else ledger,'strategy':strategy,'seed':'unit2','config':CFG,'current_step':step}
def visited(n=3,step=1,margin=1.):return {r['id']:{'visits':1,'last_step':step,'post_margin':margin} for r in POOL[:n]}


class SelectorTests(unittest.TestCase):
    def test01_random_agrees_with_v1(self):self.assertEqual(select(learner().model,state('random_once'))['selected_id'],old_select(learner().model,POOL,'random','unit2')['selected_id'])
    def test02_ambiguity_agrees_with_v1(self):self.assertEqual(select(learner().model,state())['selected_id'],old_select(learner().model,POOL,'ambiguity','unit2')['selected_id'])
    def test03_pool_order_invariant(self):
        s=state('mixed_revisit');t=copy.deepcopy(s);t['pool'].reverse();self.assertEqual(select(learner().model,s),select(learner().model,t))
    def test04_labels_in_pool_rejected(self):
        s=state();s['pool']=copy.deepcopy(POOL);s['pool'][0]['label']='0'
        with self.assertRaises(ValueError):normalize_state(s)
    def test05_labels_in_ledger_rejected(self):
        s=state(ledger=visited(1),step=100);s['ledger'][POOL[0]['id']]['label']='0'
        with self.assertRaises(ValueError):normalize_state(s)
    def test06_truth_flag_rejected(self):
        s=state(ledger=visited(1),step=100);s['ledger'][POOL[0]['id']]['correct']=False
        with self.assertRaises(ValueError):normalize_state(s)
    def test07_wrong_id_rejected(self):
        s=state();s['pool']=copy.deepcopy(POOL);s['pool'][0]['id']='0'*64
        with self.assertRaises(ValueError):normalize_state(s)
    def test08_duplicate_rejected(self):
        s=state();s['pool']=[POOL[0],POOL[0]]
        with self.assertRaises(ValueError):normalize_state(s)
    def test09_ledger_outside_pool_rejected(self):
        s=state(ledger={'0'*64:{'visits':1,'last_step':1,'post_margin':1}},step=100)
        with self.assertRaises(ValueError):normalize_state(s)
    def test10_future_step_rejected(self):
        with self.assertRaises(ValueError):normalize_state(state(ledger=visited(1,101),step=100))
    def test11_nan_margin_rejected(self):
        with self.assertRaises(ValueError):normalize_state(state(ledger=visited(1,1,float('nan')),step=100))
    def test12_visits_above2_rejected(self):
        s=state('mixed_revisit',visited(1),100);s['ledger'][POOL[0]['id']]['visits']=3
        with self.assertRaises(ValueError):normalize_state(s)
    def test13_once_cannot_have_repeats(self):
        s=state('ambiguity_once',visited(1),100);s['ledger'][POOL[0]['id']]['visits']=2
        with self.assertRaises(ValueError):normalize_state(s)
    def test14_exploration_first_slot(self):self.assertEqual(select(learner().model,state('mixed_once'))['route'],'explore')
    def test15_exploration_next_slot(self):self.assertEqual(select(learner().model,state('mixed_once',visited(1),100))['route'],'ambiguity')
    def test16_revisit_age_and_decline(self):
        q=select(learner().model,state('ambiguity_revisit',visited(),100));self.assertEqual(q['route'],'revisit');self.assertEqual(q['diagnostics']['eligible_revisits'],3)
    def test17_cooldown_blocks_revisit(self):self.assertEqual(select(learner().model,state('ambiguity_revisit',visited(step=50),100))['route'],'ambiguity')
    def test18_no_decline_no_revisit(self):self.assertEqual(select(learner().model,state('ambiguity_revisit',visited(margin=0.),100))['route'],'ambiguity')
    def test19_revisit_not_on_every_slot(self):self.assertEqual(select(learner().model,state('ambiguity_revisit',visited(2),100))['route'],'ambiguity')
    def test20_exploration_and_revisit_nonoverlap(self):
        for period in (2,4):
            self.assertTrue(all(not(i%period==0 and i%4==3) for i in range(32)))
    def test21_max_visits_blocks_revisit(self):
        ledger=visited(2);ledger[POOL[0]['id']]['visits']=2
        q=select(learner().model,state('mixed_revisit',ledger,100));self.assertEqual(q['route'],'revisit');self.assertEqual(q['selected_id'],POOL[1]['id'])
    def test22_revisit_ranks_current_margin(self):
        m=learner().model
        def raw(cs):
            a=np.zeros((len(cs),4,4))
            for i,c in enumerate(cs):a[i,:,0]=.01 if context_id(c)==POOL[1]['id'] else .2
            return {'readers':a,'checker':np.empty((len(cs),0))}
        m.raw=raw;self.assertEqual(select(m,state('ambiguity_revisit',visited(),100))['selected_id'],POOL[1]['id'])
    def test23_selection_does_not_update_weights(self):
        m=learner().model;fp=m.fingerprint
        for st in STRATEGIES:select(m,state(st))
        self.assertEqual(fp,m.fingerprint);self.assertTrue((m.readers==0).all())
    def test24_random_ignores_scores(self):
        m=learner().model;a=select(m,state('random_once'))['selected_id'];m.readers+=4;m.refresh();self.assertEqual(a,select(m,state('random_once'))['selected_id'])
    def test25_scoring_cost(self):
        self.assertEqual(select(learner().model,state('random_once'))['diagnostics']['contexts_scored_this_call'],1)
        self.assertEqual(select(learner().model,state())['diagnostics']['contexts_scored_this_call'],len(POOL))
    def test26_exhausted_once(self):
        with self.assertRaises(ValueError):select(learner().model,state('random_once',visited(6),100))
    def test27_invalid_architecture(self):
        with self.assertRaises(ValueError):select(Model('multi4'),state())
    def test28_config_strict(self):
        for change in ({'extra':1},{'explore_every':True},{'max_visits':3},{'drop_margin':.1}):
            with self.assertRaises(ValueError):validate_config(CFG|change)
    def test29_scores_not_probabilities(self):self.assertFalse(select(learner().model,state())['diagnostics']['score_is_probability'])
    def test30_reordered_fields_id_invariant(self):self.assertEqual(context_id(CONTEXTS[0]),context_id(dict(reversed(list(CONTEXTS[0].items())))))


class SessionTests(unittest.TestCase):
    def setUp(self):self.s=Session(learner(),POOL,'mixed_revisit','unit2',CFG);self.q=self.s.ask();self.fb=feedback(self.q,'0')
    def test31_budget_and_ledger(self):
        n=self.s.answer(self.q,self.fb);self.assertEqual(n.acquired,1);self.assertEqual(n.learner.step,1);self.assertEqual(set(n.selection_state['ledger'][self.q['selection']['selected_id']]),{'visits','last_step','post_margin'})
    def test32_origin_unchanged(self):
        fp=self.s.fingerprint;self.s.answer(self.q,self.fb);self.assertEqual(fp,self.s.fingerprint);self.assertEqual(self.s.learner.step,0)
    def test33_stale_request(self):
        n=self.s.answer(self.q,self.fb)
        with self.assertRaises(ValueError):n.answer(self.q,self.fb)
    def test34_tampered_selection(self):
        q=copy.deepcopy(self.q);q['selection']['context']['f0']='7'
        with self.assertRaises(ValueError):self.s.answer(q,self.fb)
    def test35_pseudo_teacher_rejected(self):
        with self.assertRaises(ValueError):self.s.answer(self.q,self.fb|{'source':'model_prediction'})
    def test36_unknown_teacher_rejected(self):
        with self.assertRaises(ValueError):self.s.answer(self.q,self.fb|{'label':'4'})
    def test37_wrong_request_rejected(self):
        with self.assertRaises(ValueError):self.s.answer(self.q,self.fb|{'request_id':'wrong'})
    def test38_extra_feedback_rejected(self):
        with self.assertRaises(ValueError):self.s.answer(self.q,self.fb|{'truth':'0'})
    def test39_background_cannot_teach_pool(self):
        with self.assertRaises(ValueError):self.s.background_question(CONTEXTS[0])
    def test40_background_advances_age_not_acquisition(self):
        s=self.s.answer(self.q,self.fb);c=CONTEXTS[0]|{'f0':'7'};q=s.background_question(c);n=s.background_answer(q,feedback(q,'1'))
        self.assertEqual(n.acquired,1);self.assertEqual(n.background_count,1);self.assertEqual(n.learner.step,2);self.assertEqual(s.selection_state['ledger'],n.selection_state['ledger'])
    def test41_background_stales_old_acquisition(self):
        c=CONTEXTS[0]|{'f0':'7'};q=self.s.background_question(c);n=self.s.background_answer(q,feedback(q,'1'))
        with self.assertRaises(ValueError):n.answer(self.q,self.fb)
    def test42_background_pseudo_rejected(self):
        q=self.s.background_question(CONTEXTS[0]|{'f0':'7'})
        with self.assertRaises(ValueError):self.s.background_answer(q,feedback(q,'1')|{'source':'model_prediction'})
    def test43_accounting_rejected(self):
        with self.assertRaises(ValueError):Session(learner(),POOL,'random_once','unit2',CFG,origin_step=1)
    def test44_save_load_resume(self):
        s=self.s.answer(self.q,self.fb)
        with tempfile.TemporaryDirectory(prefix='a2test-') as tmp:
            p=Path(tmp)/'saved';s.save(p);n=Session.load(p);self.assertEqual(n.ask(),s.ask());self.assertEqual(n.fingerprint,s.fingerprint)
            with self.assertRaises(FileExistsError):s.save(p)
    def test45_corrupt_save_rejected(self):
        with tempfile.TemporaryDirectory(prefix='a2test-') as tmp:
            p=Path(tmp)/'saved';self.s.save(p);f=p/'session.json';o=json.loads(f.read_text());o['state']['selection_state']['seed']='tampered';f.write_text(json.dumps(o))
            with self.assertRaises(ValueError):Session.load(p)
    def test46_no_replay_or_teacher_labels_in_selection_state(self):
        n=self.s.answer(self.q,self.fb);self.assertFalse(n.learner.model.entries);self.assertNotIn('label',json.dumps(n.selection_state));self.assertNotIn('correct',json.dumps(n.selection_state))
    def test47_shared_flat_equivalence(self):
        s=learner();h=np.zeros((4,512),complex)
        for c,y in [(CONTEXTS[0],'0'),(CONTEXTS[1],'1'),(CONTEXTS[2],'2')]*3:
            v=s.model.vectors([c])[0][0].reshape(-1);target=np.array([int(str(i)==y) for i in range(4)]);h+=.5*(target-(h.conj()@v).real/512)[:,None]*v;s=teach_events(s,[{'context':c,'label':y}])
        np.testing.assert_allclose(h,s.model.readers.transpose(1,0,2).reshape(4,512),atol=3e-15,rtol=0)
    def test48_teacher_declaration_not_truth_authentication(self):self.assertEqual(self.s.answer(self.q,feedback(self.q,'3')).acquired,1)


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.case=make_case('unit-data2',64)
    def test49_data_disjoint(self):self.assertTrue(validate(self.case))
    def test50_base_and_background_count(self):self.assertEqual(len(teaching(self.case,'ABC',4)),768);self.assertEqual(len(teaching(self.case,'DE',2)),256)
    def test51_changed_world_exact16(self):
        a=truth_map(self.case,'stationary');b=truth_map(self.case,'changed_pool16');self.assertEqual(sum(a[k]!=b[k] for k in a),16)
    def test52_two_worlds_first_selection_equal(self):
        s=Session(learner(),self.case['pool'],'mixed_revisit','unit2',CFG);q=s.ask();truth_map(self.case,'changed_pool16');self.assertEqual(q,s.ask())
    def test53_unknowns_excluded_from_pool(self):self.assertFalse({r['id'] for r in self.case['pool']}&{context_id(c) for c in self.case['unknown']})
    def test54_data_deterministic(self):self.assertEqual(self.case,make_case('unit-data2',64))
    def test55_empty_cohort_no_success_claim(self):
        z=np.zeros((len(probes(self.case)),4,4));m=summarize(z,self.case,'stationary',3,[],z,z,[],[],[]);self.assertEqual(m['groups']['first_block_corrected']['requests'],0)
    def test56_unknown_false_accept(self):
        z=np.zeros((len(probes(self.case)),4,4));z[:,:,0]=1;m=summarize(z,self.case,'stationary',3,[],z,z,[],[],[]);self.assertEqual(m['groups']['never_taught']['unseen_false_accept'],128);self.assertEqual(m['groups']['D']['known_requests'],0)
    def test57_corrected_cohort_relapse(self):
        rows=probes(self.case);z=np.zeros((len(rows),4,4));key=rows[0]['id'];y=int(rows[0]['label']);z[0,:,(y+1)%4]=1
        m=summarize(z,self.case,'stationary',4,[key],z,z,[key],[key],[key]);self.assertEqual(m['groups']['first_block_corrected']['tentative_wrong'],1)
    def test58_background_known_domain(self):
        z=np.zeros((len(probes(self.case)),4,4));m=summarize(z,self.case,'stationary',5,[],z,z,[],[],[]);self.assertEqual(m['groups']['E']['known_requests'],64)
    def test59_coefficients_fixed(self):self.assertEqual(learner().storage()['coefficient_bytes'],32768)
    def test60_live_timeline_and_max_revisits(self):
        base=teach_events(learner(),teaching(self.case,'ABC',4));ctx=[r['context'] for r in probes(self.case)];d=teach_events(base,teaching(self.case,'D',2));e=teach_events(d,teaching(self.case,'E',2));controls={3:base.model.raw(ctx)['readers'],4:d.model.raw(ctx)['readers'],5:e.model.raw(ctx)['readers']}
        with tempfile.TemporaryDirectory(prefix='a2run-') as tmp:
            result,times=run(base,self.case,'changed_pool16','mixed_revisit','unit2',CFG,0,controls,{},Path(tmp),False)
        self.assertEqual([s['name'] for s in result['checkpoints']],['q4','q16','post_D','q20','q32','post_E']);self.assertEqual(result['checkpoints'][2]['background_count'],128);self.assertEqual(result['checkpoints'][-1]['learner_step'],1056)
        self.assertEqual(sum(r['request']['selection']['route']=='revisit' for r in result['trace'][:16]),0)
        self.assertTrue(all(result['checks'].values()))
    def test61_revisit_toggle_same_first16_teachers(self):
        truth=truth_map(self.case,'stationary')
        for prefix in ('ambiguity','mixed'):
            a=Session(learner(),self.case['pool'],prefix+'_once','unit2',CFG);b=Session(learner(),self.case['pool'],prefix+'_revisit','unit2',CFG)
            for _ in range(16):
                qa=a.ask();qb=b.ask();key=qa['selection']['selected_id'];self.assertEqual(key,qb['selection']['selected_id']);a=a.answer(qa,feedback(qa,truth[key]));b=b.answer(qb,feedback(qb,truth[key]))
            np.testing.assert_array_equal(a.learner.model.readers,b.learner.model.readers)
    def test62_development_tie_break_predeclared(self):
        grid=[CFG|{'explore_every':period,'drop_margin':drop} for period in (2,4) for drop in (.05,.15)];runs=[]
        for i in range(4):
            for _ in range(4):runs.append({'config_index':i,'strategy':'mixed_revisit','size':64,'checkpoints':[{'metrics':{'groups':{'old_all':{'accepted_correct':128,'accepted_wrong':0},'never_taught':{'unseen_false_accept':0},'protected_old':{'accepted_correct':64}}}}]})
        result=choose({'runs':runs,'result_digest':'unit'},{'configuration_grid':grid,'configuration_selection':'unit'})
        self.assertEqual(result['config_index'],3);self.assertEqual(result['development_rows'][0]['utility'],1.5)


if __name__=='__main__':unittest.main()
