import copy,itertools,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from evaluation.support import data,parse,expected
from evaluation.language import training_case
from evaluation.synthetic import pairs
from evaluation.metrics import score,equal_count
from plm_l1_v010.selection import select_candidates
from plm_l1_v010.memory import fit_memory,calibrate_gate
from plm_l1_v010.training import fit
from plm_l1_v010.runtime import CommitteeModel,PACKET_SCHEMA
from plm_l1_v010.base.runtime import TemporalModel,PACKET_FIELDS
from plm_l1_v010.base.component.runtime import Model as ComponentModel
from plm_l1_v010.base.component.banked import MemoryBlock,BankedMemory,META_BYTES
from plm_l1_v010.base.component.algebra import canonical
from plm_l1_v010.portability import compare
from plm_l1_v010 import policy

def perturb(model,amount):
    members=list(model.members); original=members[0]
    memories=dict(original.component.memories); blocks=list(memories['roles'].blocks); raw=blocks[0].blob
    weights=np.frombuffer(raw,dtype='<c16',offset=META_BYTES).copy()
    if amount=='ulp':weights.real[0]=np.nextafter(weights.real[0],np.inf)
    else:weights[0]+=amount
    blocks[0]=MemoryBlock(raw[:META_BYTES]+weights.tobytes()); memories['roles']=BankedMemory(blocks)
    comp=ComponentModel(original.component.meta,memories)
    members[0]=TemporalModel(comp,original.memories,original.meta['training'],dimension=original.meta['dimension'],seed=original.meta['seed'],mode=original.meta['mode'])
    return CommitteeModel(members,model.meta['training'])

class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.task=data('ambiguity_development')[0]
    def candidate(self,**kw):
        return fit_memory(pairs(self.task['train']),pairs(self.task['selection_validation']),seed='candidate-development-0',**kw)
    def test_two_indistinguishable_fields_retained(self):
        m=self.candidate(); self.assertEqual(len(m.memories),2); self.assertTrue(m.supported)
    def test_disagreement_veto(self):
        m=self.candidate()
        for r in self.task['evaluation']:
            p=m.predict(r['context']); self.assertIsNone(p['value']); self.assertEqual(len({h['value'] for h in p['members']}),2)
    def test_added_examples_resolve_without_test_labels(self):
        m=fit_memory(pairs(self.task['train']+self.task['added_examples']),pairs(self.task['selection_validation']),seed='candidate-development-0')
        self.assertEqual(len(m.memories),1)
        for r in self.task['evaluation']:self.assertEqual(m.predict(r['context'])['value'],r['label'])
    def test_symbolic_matched_candidate_family(self):
        s=self.candidate(); t=self.candidate(method='symbolic_multi')
        self.assertEqual(s.audit['selected_masks'],t.audit['selected_masks'])
        self.assertEqual([x.blocks[0].blob for x in s.memories],[x.blocks[0].blob for x in t.memories])
    def test_single_keeps_first_candidate_only(self):
        m=self.candidate(method='ss_single');self.assertEqual(len(m.memories),1)
    def test_zero_selection_signal_unsupported(self):
        m=self.candidate(selection_enabled=False);self.assertFalse(m.supported)
        self.assertTrue(all(m.predict(r['context'])['value'] is None for r in self.task['evaluation']))
    def test_overflow_is_not_silent_four_candidate_certainty(self):
        rows=[(dict.fromkeys(['f'+str(i) for i in range(6)],v),str(v)) for v in (0,1)]
        m=fit_memory(rows,rows,seed='overflow-test')
        self.assertEqual(m.audit['plausible_minimal_count'],6);self.assertTrue(m.audit['overflow'])
        self.assertEqual(len(m.memories),4);self.assertIsNone(m.predict(rows[0][0])['value'])
    def test_no_id3_in_new_selection(self):
        with patch('plm_l1_v010.base.component.projection.dependency_leaves',side_effect=AssertionError('ID3')):self.candidate()
    def test_no_validation_oracle_annotation_argument(self):
        with self.assertRaises(TypeError):select_candidates(pairs(self.task['train']),pairs(self.task['selection_validation']),true_dependencies=['f1'])
    def test_validation_labels_change_selection_not_weight_training(self):
        a=self.candidate()
        val=[(r['context'],'label:1' if r['label']=='label:0' else 'label:0') for r in self.task['selection_validation']]
        b=fit_memory(pairs(self.task['train']),val,seed='candidate-development-0')
        self.assertFalse(b.supported);self.assertTrue(a.supported)
    def test_training_perfection_relaxed(self):
        task=next(t for t in data('dependencies_development') if t['id']=='development/unary/0/24/3')
        m=fit_memory(pairs(task['train']),pairs(task['selection_validation']),seed='candidate-development-0')
        chosen=[t for t in m.audit['trials'] if t['mask'] in m.audit['selected_masks']]
        self.assertTrue(m.supported);self.assertTrue(any(t['train']['correct']<t['train']['requests'] for t in chosen))
    def test_four_way_context_disjointness(self):
        for split in ('development','evaluation'):
            for name in ('dependencies','ambiguity'):
                for t in data(name+'_'+split):
                    sets=[{canonical(r['context']) for r in t[k]} for k in ('train','selection_validation','risk_calibration','evaluation')]
                    if 'added_examples' in t:sets.append({canonical(r['context']) for r in t['added_examples']})
                    self.assertTrue(all(not a&b for a,b in itertools.combinations(sets,2)))
    def test_fixed_numeric_budget(self):
        a=self.candidate(dimension=512);b=self.candidate(dimension=512,budget='fixed_total')
        self.assertEqual(a.storage()['numerical_weight_bytes'],16*1024)
        self.assertEqual(b.storage()['numerical_weight_bytes'],16*512)
        self.assertEqual(b.audit['each_candidate_dimension'],256)
    def test_invalid_options(self):
        for kw in ({'method':'unknown'},{'budget':'magic'},{'dimension':127}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):self.candidate(**kw)
    def test_independent_model_memories(self):
        m=self.candidate();self.assertIsNot(m.memories[0],m.memories[1]);self.assertIsNot(m.memories[0].blocks[0],m.memories[1].blocks[0])
    def test_ood_is_not_probability_zero(self):
        m=self.candidate();p=m.predict(dict.fromkeys(self.task['train'][0]['context'],2))
        self.assertIsNone(p['value']);self.assertNotIn('probability',p)
    def test_calibration_does_not_see_evaluation(self):
        m=self.candidate();before=[b.blob for x in m.memories for b in x.blocks]
        c=calibrate_gate(m,pairs(self.task['risk_calibration']))
        self.assertFalse(c['statistical_risk_guarantee']);self.assertEqual(c['calibration_requests'],4)
        self.assertEqual(before,[b.blob for x in m.memories for b in x.blocks])
    def test_finite_calibration_can_fail_under_shift(self):
        m=self.candidate(method='ss_single');calibrate_gate(m,pairs(self.task['risk_calibration']))
        self.assertTrue(all(m.predict(r['context'])['value']!=r['label'] for r in self.task['evaluation']))
    def test_unanimity_is_not_external_truth(self):
        m=self.candidate();r=self.task['train'][0];out=m.predict(r['context'])
        self.assertIsNotNone(out['value']);self.assertNotEqual(out['value'],'unprovided_external_truth')
    def test_no_answer_risk_is_undefined(self):self.assertIsNone(score([None,None],['a','b'])['selective_risk'])
    def test_accounting_requires_equal_lengths(self):
        with self.assertRaises(ValueError):score([],['a'])
    def test_equal_count_cannot_win_by_abstaining_all(self):
        r=equal_count(self.task['evaluation'],{'a':[None]*8,'b':['x']*8});self.assertEqual(r['status'],'no_positive_common_coverage')

class LanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.standard=fit(data('component_train'),data('single_development'),data('temporal_train'),data('lexicon'),selection_seed='candidate-development-0')
        cls.before=fit(*training_case(False),data('lexicon'),selection_seed='candidate-development-0')
        cls.after=fit(*training_case(True),data('lexicon'),selection_seed='candidate-development-0')
        cls.text='太郎が花子を助けた。その後、花子が健太を褒めた。'
        cls.packet=cls.standard.read(cls.text)['packet']
        cls.meaning=cls.standard.recover(cls.packet)['meaning']
        cls.cross=copy.deepcopy(cls.meaning);cls.cross['events'][0]['polarity']='polarity:negative'
    def test_standard_has_two_actual_pipelines(self):self.assertEqual(len(self.standard.members),2)
    def test_numeric_packet_fields_only(self):
        self.assertEqual(set(self.packet),PACKET_FIELDS);self.assertEqual(self.packet['schema'],PACKET_SCHEMA);self.assertFalse(self.packet['eligible_for_inference'])
    def test_reverse_time_preserved(self):
        g=self.standard.generate(self.packet,('object','subject'),'reverse')
        self.assertEqual(parse(g['text']),expected(self.meaning,('object','subject'),'reverse'))
    def test_ambiguous_generation_is_atomic(self):
        out=self.before.generate(self.before.encode(self.cross))
        self.assertEqual(out['reason'],'candidate_generation_disagreement');self.assertIsNone(out['text'])
        self.assertEqual(len({x['text'] for x in out['candidate_audit']}),2)
    def test_joint_candidate_overflow_vetoes_even_agreement(self):
        self.assertEqual(self.before.meta['training']['joint_plausible_count'],8)
        self.assertEqual(len(self.before.members),4)
        self.assertFalse(self.before.meta['training']['supported'])
        out=self.before.generate(self.before.encode(self.meaning))
        self.assertEqual(out['status'],'abstain');self.assertIsNone(out['text'])
    def test_added_two_pairs_enable_correct_generation(self):
        out=self.after.generate(self.after.encode(self.cross));self.assertEqual(parse(out['text']),expected(self.cross,('subject','subject')))
        self.assertEqual(self.after.meta['training']['component_pairs']-self.before.meta['training']['component_pairs'],2)
    def test_after_refit_old_packet_rejected(self):
        self.assertEqual(self.after.recover(self.before.encode(self.cross))['status'],'abstain')
    def test_two_pair_update_does_not_consume_test_rows(self):
        train,val,time=training_case(False)
        self.assertTrue(all((e['polarity']=='polarity:negative')==(e['modality']=='modality:hypothetical') for r in time for e in r['meaning']['events']))
        added=set(r['text'] for r in training_case(True)[0])-set(r['text'] for r in train)
        self.assertFalse(added&{r['text'] for r in val});self.assertFalse(added&{r['text'] for r in data('single_evaluation')})
    def test_read_uncertainty_does_not_emit_packet(self):
        out=self.before.read(self.text.replace('助けた','助けなかった'))
        self.assertEqual(out['status'],'abstain');self.assertIsNone(out['packet'])
    def test_complete_meaning_disagreement(self):
        second=self.standard.members[1];wrong=copy.deepcopy(self.meaning);wrong['events'][0]['polarity']='polarity:negative'
        with patch.object(second,'read',return_value={'status':'read','packet':second.encode(wrong)}):
            out=self.standard.read(self.text)
        self.assertEqual(out['reason'],'candidate_meaning_disagreement');self.assertIsNone(out['packet'])
    def test_one_unsupported_member_cannot_be_ignored(self):
        with patch.object(self.standard.members[1],'read',return_value={'status':'abstain','reason':'weak'}):out=self.standard.read(self.text)
        self.assertEqual(out['reason'],'candidate_read_unsupported')
    def test_no_candidate_slot_splicing(self):
        original=self.standard.members[1]
        with patch.object(original,'generate',return_value={'status':'generated','text':'別の候補文。','eligible_for_inference':False}):
            out=self.standard.generate(self.packet)
        self.assertIsNone(out['text']);self.assertEqual(out['reason'],'candidate_generation_disagreement')
    def test_unsupported_family_cannot_confirm(self):
        m=CommitteeModel(list(self.standard.members),dict(self.standard.meta['training'],supported=False))
        self.assertEqual(m.read(self.text)['status'],'abstain');self.assertEqual(m.generate(m.encode(self.meaning))['status'],'abstain')
    def test_invalid_member_count(self):
        for members in ([],list(self.standard.members)*3):
            with self.assertRaises(ValueError):CommitteeModel(members,self.standard.meta['training'])
    def test_new_and_base_packet_namespaces_distinct(self):
        self.assertEqual(self.standard.recover(self.standard.members[0].encode(self.meaning))['status'],'abstain')
    def test_unexpected_fields_and_fingerprint(self):
        for p in (dict(self.packet,text=self.text),dict(self.packet,model_fingerprint='wrong')):self.assertEqual(self.standard.recover(p)['status'],'abstain')
    def test_negative_and_nonfinite_signal(self):
        for value in (float('nan'),float('inf'),True):
            p=copy.deepcopy(self.packet);p['real'][0]=value;self.assertEqual(self.standard.recover(p)['status'],'abstain')
        p=dict(self.packet,real=[-x for x in self.packet['real']],imag=[-x for x in self.packet['imag']])
        self.assertEqual(self.standard.recover(p)['status'],'abstain')
    def test_no_runtime_learning(self):
        with patch('plm_l1_v010.selection.select_candidates',side_effect=AssertionError('learning')):self.assertEqual(self.standard.generate(self.packet)['status'],'generated')
    def test_same_entity_inference_boundary_retained(self):self.assertEqual(self.standard.read(self.text.replace('太郎が花子を','太郎が太郎を'))['status'],'read')
    def test_three_events_not_opened(self):self.assertEqual(self.standard.read(self.text+'太郎が花子を助けた。')['status'],'abstain')
    def test_strict_save_reload_and_inventory(self):
        with tempfile.TemporaryDirectory(prefix='l10-') as d:
            self.standard.save(d);m=CommitteeModel.load(d);self.assertEqual(m.fingerprint,self.standard.fingerprint)
            with (Path(d)/'extra').open('x') as f:f.write('test')
            with self.assertRaisesRegex(ValueError,'invalid_member_inventory'):CommitteeModel.load(d)
    def test_fingerprint_excludes_timing_and_heap(self):
        s=canonical(self.standard.meta)
        self.assertNotIn('wall_seconds',s);self.assertNotIn('owned_heap_bytes',s);self.assertEqual(self.standard.meta['policy'],policy.values())
    def test_ulp_functional_but_not_strict(self):
        m=perturb(self.standard,'ulp');r=compare(self.standard,m,[self.text,''])
        self.assertTrue(r['functional_passed']);self.assertFalse(r['exact_fingerprint_equal'])
        self.assertEqual(m.recover(self.packet)['status'],'abstain')
    def test_large_coefficient_difference_rejected(self):self.assertFalse(compare(self.standard,perturb(self.standard,.01),[self.text])['functional_passed'])
    def test_decision_equality_required(self):
        m=perturb(self.standard,'ulp')
        with patch.object(m,'read',return_value={'status':'abstain','reason':'decision_changed'}):r=compare(self.standard,m,[self.text])
        self.assertFalse(r['functional_passed'])

if __name__=='__main__':unittest.main()
