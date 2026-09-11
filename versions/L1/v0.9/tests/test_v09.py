import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from evaluation.support import data,six_pairs,parse,expected,ROOT
from evaluation.synthetic import symbolic_predict
from plm_l1_v09.selection import select,trial,unique_rows
from plm_l1_v09.component.training import fit as fit_component
from plm_l1_v09.component.runtime import Model
from plm_l1_v09.component.algebra import canonical
from plm_l1_v09.component.banked import BankedMemory,MemoryBlock,META_BYTES,fit_banked
from plm_l1_v09.training import fit
from plm_l1_v09.runtime import TemporalModel,PACKET_FIELDS
from plm_l1_v09.portability import compare
from plm_l1_v09.thresholds import values,MIN_SCORE

def changed(model,amount):
    memories=dict(model.component.memories); blocks=list(memories['roles'].blocks)
    raw=blocks[0].blob; x=np.frombuffer(raw,dtype='<c16',offset=META_BYTES).copy()
    if amount=='ulp': x.real[0]=np.nextafter(x.real[0],np.inf)
    else: x[0]+=amount
    blocks[0]=MemoryBlock(raw[:META_BYTES]+x.tobytes()); memories['roles']=BankedMemory(blocks)
    component=Model(model.component.meta,memories)
    return TemporalModel(component,model.memories,model.meta['training'],dimension=model.meta['dimension'],seed=model.meta['seed'],mode=model.meta['mode'])

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows=[({'a':a,'b':b,'noise':n},str(a^b)) for a,b,n in itertools.product((0,1),repeat=3)]

    def test_xor_phase_selects_joint_fields(self):
        leaves,audit=select(self.rows,seed='test-selector')
        self.assertEqual(audit['selected_masks'],[('a','b')])
        self.assertEqual(audit['selected_contexts'],4)

    def test_symbolic_matched_search(self):
        s,sa=select(self.rows,seed='test-selector'); t,ta=select(self.rows,method='symbolic')
        self.assertEqual(s,t); self.assertEqual(len(sa['trials']),len(ta['trials']))

    def test_zero_phase_does_not_select(self):
        _,a=select(self.rows,enabled=False)
        self.assertTrue(a['fallback_full_context']); self.assertFalse(any(t['eligible'] for t in a['trials']))

    def test_no_id3_called_in_ss_branch(self):
        with patch('plm_l1_v09.component.projection.dependency_leaves',side_effect=AssertionError('ID3')):
            select(self.rows)

    def test_no_id3_called_in_ss_component_fit(self):
        with patch('plm_l1_v09.component.banked.dependency_leaves',side_effect=AssertionError('ID3')):
            fit_component(six_pairs(),data('lexicon'),selector='ss')

    def test_no_purity_acceptance_for_conflicting_labels(self):
        _,a=select([({'a':0},'x'),({'a':0},'y')])
        self.assertTrue(a['fallback_full_context'])

    def test_repetition_does_not_change_decision(self):
        x,a=select(self.rows); y,b=select(self.rows*5)
        self.assertEqual(x,y); self.assertEqual(a['trials'],b['trials'])

    def test_positive_only_keeps_support_key(self):
        rows=[(c,'yes') for c,_ in self.rows]; _,a=select(rows)
        self.assertEqual(a['selection_status'],'positive_only_full_context')
        self.assertEqual(a['selected_masks'],[('a','b','noise')])

    def test_unknown_relevant_value_not_registered(self):
        leaves,_=select(self.rows); m,_=fit_banked(self.rows,8192,'test',selected_leaves=leaves)
        self.assertIsNone(m.recall({'a':2,'b':2,'noise':0})['value'])

    def test_missing_key_field_not_numeric_partial_observation(self):
        leaves,_=select(self.rows); m,_=fit_banked(self.rows,8192,'test',selected_leaves=leaves)
        with self.assertRaisesRegex(ValueError,'missing_query_field'): m.recall({'a':0})

    def test_conditional_mean_not_duplicate_gain(self):
        leaves=[({'a':0},'x')]*7+[({'a':1},'y')]*3
        x,_=fit_banked(leaves,2048,'test',selected_leaves=leaves)
        y,_=fit_banked(leaves,2048,'test',selected_leaves=[({'a':0},'x'),({'a':1},'y')])
        self.assertEqual(x.blocks[0].blob,y.blocks[0].blob)

    def test_ambiguous_full_key_abstains(self):
        rows=[({'a':0},'x'),({'a':0},'y')]
        m,_=fit_banked(rows,8192,'test',selected_leaves=rows)
        self.assertIsNone(m.recall({'a':0})['value'])

    def test_invalid_settings(self):
        for args in ({'dimension':127},{'dimension':True},{'method':'entropy'},{'enabled':1},{'seed':''}):
            with self.subTest(args=args),self.assertRaises(ValueError): select(self.rows,**args)
        for rows in ([],[None],[({},'x')],[({'a':0},3)],[({'a':0},'x'),({'b':0},'x')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError): select(rows)

    def test_only_training_pairs_enter_selector(self):
        with self.assertRaises(TypeError): select(self.rows,true_dependencies=['a','b'])

    def test_synthetic_data_disjoint_and_closed(self):
        for split in ('development','evaluation'):
            for task in data('dependencies_'+split):
                train={canonical(r['context']) for r in task['train']}; test={canonical(r['context']) for r in task['test']}
                self.assertFalse(train&test); self.assertEqual(len(train),task['train_count']); self.assertEqual(len(test),8)

class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=fit(data('component_train'),data('temporal_train'),data('lexicon'),seed='temporal-evaluation-0',selection_seed='selection-evaluation-0')
        cls.text='太郎が花子を助けた。その後、花子が健太を褒めた。'
        cls.read=cls.model.read(cls.text); cls.packet=cls.read['packet']

    def test_default_model_actually_uses_ss(self):
        self.assertEqual(self.model.component.meta['dependency_selection'],'ss')
        self.assertEqual(self.model.component.meta['statistics']['gaps']['projected_contexts'],16)

    def test_pair_learning_rule_inventory(self):
        stats=self.model.component.meta['statistics']
        self.assertEqual(sum(s['projected_contexts'] for n,s in stats.items() if not n.startswith('lexical_')),32)
        self.assertEqual(sum(s['projected_contexts'] for n,s in stats.items() if n.startswith('lexical_')),20)

    def test_no_heap_or_timing_in_fingerprint_metadata(self):
        text=canonical(self.model.meta)+canonical(self.model.component.meta)
        self.assertNotIn('owned_heap_bytes',text); self.assertNotIn('wall_seconds',text)

    def test_threshold_registry_is_shared(self):
        from plm_l1_v09 import codec,selection
        from plm_l1_v09.component import banked,runtime
        for module in (codec,selection,banked,runtime): self.assertEqual(module.MIN_SCORE,values()['MIN_SCORE'])
        self.assertEqual(self.model.meta['thresholds'],values())
        self.assertEqual(self.model.component.meta['thresholds'],values())

    def test_changed_threshold_metadata_rejected(self):
        meta=copy.deepcopy(self.model.component.meta); meta['thresholds']['MIN_SCORE']=0.1
        with self.assertRaisesRegex(ValueError,'threshold_policy_mismatch'): Model(meta,self.model.component.memories)

    def test_packet_is_numeric_only_and_inference_closed(self):
        self.assertEqual(set(self.packet),PACKET_FIELDS)
        self.assertFalse(self.packet['eligible_for_inference'])
        self.assertTrue(all(type(v) is float for f in ('real','imag') for v in self.packet[f]))

    def test_negative_signal_rejected(self):
        p=dict(self.packet,real=[-v for v in self.packet['real']],imag=[-v for v in self.packet['imag']])
        self.assertEqual(self.model.recover(p)['reason'],'event_presence_weak')

    def test_extra_field_and_wrong_fingerprint_rejected(self):
        for p in (dict(self.packet,text=self.text),dict(self.packet,model_fingerprint='wrong')):
            self.assertEqual(self.model.recover(p)['status'],'abstain')

    def test_nonfinite_signal_rejected(self):
        for value in (float('nan'),float('inf'),True):
            p=copy.deepcopy(self.packet); p['real'][0]=value
            self.assertEqual(self.model.recover(p)['status'],'abstain')

    def test_atomic_read_abstention(self):
        out=self.model.read('太郎が花子を助けた。その後、彼が花子を助けた。')
        self.assertEqual(out['status'],'abstain'); self.assertIsNone(out['packet'])

    def test_component_text_consistency_is_distinct(self):
        out=self.model.component.read('もし太郎が花子を助けた。')
        self.assertEqual(out['status'],'abstain')
        good=self.model.component.read('太郎が花子を助けた。')
        self.assertEqual(good['verification']['method'],'recover_equals_candidate')

    def test_reverse_presentation_preserves_time(self):
        m=self.model.recover(self.packet)['meaning']; g=self.model.generate(self.packet,('object','subject'),'reverse')
        self.assertEqual(parse(g['text']),expected(m,('object','subject'),'reverse'))
        self.assertIn('その前に、',g['text'])

    def test_unknown_time_stays_unknown(self):
        text=self.text.replace('その後、',''); r=self.model.read(text)
        self.assertEqual(self.model.recover(r['packet'])['meaning']['temporal']['kind'],'unknown')
        self.assertNotIn('その前に',self.model.generate(r['packet'],order='reverse')['text'])

    def test_same_entity_inference_and_training_boundary(self):
        text='太郎が太郎を助けた。'; out=self.model.component.read(text)
        self.assertEqual(out['status'],'read')
        m=self.model.component.recover(out['packet'])['meaning']; self.assertEqual(m['subject'],m['object'])
        with self.assertRaisesRegex(ValueError,'ambiguous_or_repeated_alignment'): fit_component([{'text':text,'meaning':m}],data('lexicon'))

    def test_three_events_not_opened(self):
        self.assertEqual(self.model.read(self.text+'太郎が花子を助けた。')['status'],'abstain')

    def test_runtime_does_not_select_features(self):
        with patch('plm_l1_v09.selection.select',side_effect=AssertionError('learning')):
            self.assertEqual(self.model.generate(self.packet)['status'],'generated')

    def test_saved_model_exact_reload(self):
        with tempfile.TemporaryDirectory(prefix='l09-') as folder:
            self.model.save(folder); m=TemporalModel.load(folder)
            self.assertEqual(m.fingerprint,self.model.fingerprint)
            self.assertTrue(compare(self.model,m,[self.text])['functional_passed'])

    def test_tiny_difference_functional_not_exact(self):
        other=changed(self.model,'ulp'); report=compare(self.model,other,[self.text,''])
        self.assertTrue(report['functional_passed']); self.assertFalse(report['exact_weight_bytes_equal'])
        self.assertFalse(report['exact_model_fingerprint_equal'])
        self.assertEqual(other.recover(self.packet)['status'],'abstain')

    def test_large_difference_fails_functional(self):
        report=compare(self.model,changed(self.model,0.01),[self.text])
        self.assertFalse(report['functional_passed']); self.assertFalse(report['coefficients_within_tolerance'])

    def test_exact_decisions_required_even_if_coefficients_equal(self):
        other=changed(self.model,'ulp')
        with patch.object(other,'read',return_value={'status':'abstain','reason':'boundary_decision_change'}):
            report=compare(self.model,other,[self.text])
        self.assertTrue(report['coefficients_within_tolerance']); self.assertFalse(report['functional_passed'])

    def test_semantic_signal_residual_gate(self):
        p=dict(self.packet,real=[2*v for v in self.packet['real']],imag=[2*v for v in self.packet['imag']])
        self.assertEqual(self.model.recover(p)['status'],'abstain')

if __name__=='__main__': unittest.main()
