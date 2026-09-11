import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import canonical
from plm_l1_v06.runtime import Model as ComponentModel
from plm_l1_v08.runtime import TemporalModel,PACKET_FIELDS
from plm_l1_v08.training import fit
from plm_l1_v08.codec import TemporalCodec
from plm_l1_v08.contract import normalize,split_document,IDS,TIMES,PRESENTATIONS
from evaluation_support import data,GOALS,parse,expected,to_mentions,unique_meanings,V07
from measurements import INVALID_TEXTS,bad_packets,count,learning_controls,noise_rng


class TemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=fit(data('component_train'),data('temporal_train'),data('lexicon'))
        cls.rows=data('development')
        cls.text='太郎が花子を助けた。その後、花子が健太を褒めた。'
        r=cls.model.read(cls.text)
        cls.packet=r['packet']; cls.meaning=cls.model.recover(cls.packet)['meaning']

    def test_development_read_all(self):
        for row in self.rows:
            r=self.model.read(row['text'])
            self.assertEqual(r['status'],'read',row['id'])
            self.assertEqual(self.model.recover(r['packet'])['meaning'],to_mentions(row['meaning']))

    def test_development_direct_generation_all_orders_and_goals(self):
        for row in unique_meanings(self.rows):
            for order in ('preserve','reverse'):
                for goals in GOALS:
                    r=self.model.generate(self.model.encode(row['meaning']),goals,order)
                    self.assertEqual(parse(r['text']),expected(row['meaning'],goals,order),row['id'])

    def test_reverse_changes_marker_not_time(self):
        out=self.model.generate(self.packet,order='reverse')
        self.assertEqual(out['text'],'花子が健太を褒めた。その前に、太郎が花子を助けた。')
        self.assertEqual(out['event_order'],['event:1','event:0'])

    def test_same_time_different_mention_order(self):
        r=self.model.read('花子が健太を褒めた。その前に、太郎が花子を助けた。')
        m=self.model.recover(r['packet'])['meaning']
        self.assertEqual(m['temporal'],TIMES[2])
        self.assertEqual(self.model.generate(r['packet'],order='reverse')['text'],self.text)

    def test_after_not_assumed_from_mention_order(self):
        text='太郎が花子を助けた。花子が健太を褒めた。'
        r=self.model.read(text); m=self.model.recover(r['packet'])['meaning']
        self.assertEqual(m['temporal'],TIMES[0])
        self.assertEqual(self.model.generate(r['packet'],order='reverse')['text'],'花子が健太を褒めた。太郎が花子を助けた。')

    def test_before_after_unknown_distinct(self):
        packets=[self.model.read(self.text.replace('その後、',marker))['packet'] for marker in ('その後、','その前に、','')]
        self.assertEqual(len({canonical(p) for p in packets}),3)

    def test_negation_and_hypothesis_remain_event_local(self):
        text='もし太郎が花子を助けなかったら。その後、花子が健太を褒めた。'
        r=self.model.read(text)
        out=self.model.generate(r['packet'],['object','subject'],'reverse')
        self.assertEqual(out['text'],'健太を花子が褒めた。その前に、もし太郎が花子を助けなかったら。')

    def test_identical_occurrences_not_deduplicated(self):
        text='太郎が花子を助けた。その後、太郎が花子を助けた。'
        r=self.model.read(text); m=self.model.recover(r['packet'])['meaning']
        self.assertEqual(len(m['events']),2)
        self.assertEqual([e['id'] for e in m['events']],list(IDS))
        self.assertEqual(self.model.generate(r['packet'],order='reverse')['text'],'太郎が花子を助けた。その前に、太郎が花子を助けた。')

    def test_event_list_storage_order_is_not_presentation(self):
        m=copy.deepcopy(self.meaning); m['events'].reverse()
        self.assertEqual(self.model.encode(m),self.packet)

    def test_presentation_change_preserves_fixed_edge(self):
        m=copy.deepcopy(self.meaning); m['presentation'].reverse()
        p=self.model.encode(m)
        self.assertNotEqual(p,self.packet)
        self.assertEqual(self.model.recover(p)['meaning']['temporal'],self.meaning['temporal'])
        self.assertIn('その前に、',self.model.generate(p)['text'])

    def test_edge_change_does_not_swap_event_frames(self):
        m=copy.deepcopy(self.meaning); m['temporal']=copy.deepcopy(TIMES[2])
        recovered=self.model.recover(self.model.encode(m))['meaning']
        self.assertEqual(recovered['events'],self.meaning['events'])
        self.assertEqual(recovered['presentation'],self.meaning['presentation'])
        self.assertNotEqual(recovered['temporal'],self.meaning['temporal'])

    def test_alpha_rename_ids_and_endpoints(self):
        m=copy.deepcopy(self.meaning)
        rename=dict(zip(IDS,reversed(IDS)))
        for e in m['events']: e['id']=rename[e['id']]
        m['presentation']=[rename[i] for i in m['presentation']]
        for k in ('source','target'): m['temporal'][k]=rename[m['temporal'][k]]
        self.assertEqual(self.model.generate(self.model.encode(m))['text'],self.text)

    def test_undirected_control_loses_edge_direction_exactly(self):
        c=TemporalCodec(self.model.codec.candidates,mode='undirected')
        m=copy.deepcopy(self.meaning); m['temporal']=copy.deepcopy(TIMES[2])
        self.assertTrue(np.array_equal(c.encode(m),c.encode(self.meaning)))
        with self.assertRaisesRegex(ValueError,'temporal_signal_ambiguous'): c.recover(c.encode(m))

    def test_partitioned_equal_payload_and_recovery(self):
        c=TemporalCodec(self.model.codec.candidates,mode='partitioned')
        self.assertEqual(c.encode(self.meaning).nbytes,self.model.codec.encode(self.meaning).nbytes)
        self.assertEqual(c.recover(c.encode(self.meaning))['meaning'],self.meaning)

    def test_missing_time_signal_is_not_unknown(self):
        c=self.model.codec; v=c.encode(self.meaning)-c.components(self.meaning)[2]*c.scale
        p=dict(self.packet,real=v.real.tolist(),imag=v.imag.tolist())
        self.assertEqual(self.model.recover(p)['status'],'abstain')

    def test_missing_presentation_signal_rejected(self):
        c=self.model.codec; v=c.encode(self.meaning)-c.components(self.meaning)[3]*c.scale
        self.assertEqual(self.model.recover(dict(self.packet,real=v.real.tolist(),imag=v.imag.tolist()))['status'],'abstain')

    def test_missing_event_frame_rejected(self):
        c=self.model.codec; v=c.encode(self.meaning)-c.components(self.meaning)[1]*c.scale
        self.assertEqual(self.model.recover(dict(self.packet,real=v.real.tolist(),imag=v.imag.tolist()))['status'],'abstain')

    def test_complete_numeric_packet_only(self):
        self.assertEqual(set(self.packet),PACKET_FIELDS)
        self.assertEqual(len(self.packet['real']),8192)
        for word in ('太郎','temporal','presentation','before','event:0'):
            if word!='temporal': self.assertNotIn(word,canonical(self.packet))
        self.assertNotIn('meaning',self.packet)

    def test_invalid_packets_all_abstain(self):
        for p in bad_packets(self.model,self.meaning): self.assertEqual(self.model.generate(p)['status'],'abstain')

    def test_source_gold_relation_hint_fields_rejected(self):
        for field in ('text','source_text','gold','temporal','presentation','subpackets','event_hints'):
            self.assertEqual(self.model.recover(dict(self.packet,**{field:'hint'}))['status'],'abstain')

    def test_old_packet_incompatible(self):
        from plm_l1_v07.runtime import EventModel
        old=EventModel(self.model.component)
        meaning={'events':[{k:v for k,v in e.items() if k!='id'} for e in self.meaning['events']]}
        self.assertEqual(self.model.generate(old.encode(meaning))['status'],'abstain')

    def test_cross_seed_mode_packet_incompatible(self):
        for mode in ('partitioned','undirected'):
            m=TemporalModel(self.model.component,self.model.memories,self.model.meta['training'],mode=mode)
            self.assertEqual(m.recover(self.packet)['reason'],'packet_model_mismatch')

    def test_invalid_event_fields(self):
        for m in (None,{},[],{'events':[]},dict(self.meaning,gold=True)):
            with self.assertRaises(ValueError): self.model.encode(m)

    def test_event_ids_unique_and_closed(self):
        for value in ('event:0','outside',None,[],1):
            m=copy.deepcopy(self.meaning); m['events'][1]['id']=value
            with self.assertRaises(ValueError): self.model.encode(m)

    def test_exactly_two_events(self):
        for n in (0,1,3):
            m=copy.deepcopy(self.meaning); m['events']=(m['events']*2)[:n]
            with self.assertRaises(ValueError): self.model.encode(m)

    def test_temporal_schema_closed(self):
        for t in ({'kind':'after','source':IDS[0],'target':IDS[1]}, {'kind':'cause','source':IDS[0],'target':IDS[1]},
                  {'kind':'unknown','source':IDS[0],'target':IDS[1]}, {'kind':'before','source':IDS[0],'target':IDS[0]}, {},None):
            m=copy.deepcopy(self.meaning); m['temporal']=t
            with self.assertRaises(ValueError): self.model.encode(m)

    def test_invalid_presentation(self):
        for p in ([],list(IDS)+[IDS[0]],[IDS[0],IDS[0]],'event:0',None):
            m=copy.deepcopy(self.meaning); m['presentation']=p
            with self.assertRaises(ValueError): self.model.encode(m)

    def test_unknown_event_value(self):
        m=copy.deepcopy(self.meaning); m['events'][0]['subject']='entity:未知'
        with self.assertRaises(ValueError): self.model.encode(m)

    def test_input_not_mutated(self):
        m=copy.deepcopy(self.meaning); p=copy.deepcopy(self.packet)
        self.model.encode(m); self.model.generate(p,order='reverse')
        self.assertEqual(m,self.meaning); self.assertEqual(p,self.packet)

    def test_invalid_documents(self):
        for text in INVALID_TEXTS+(None,[],True,1): self.assertEqual(self.model.read(text)['status'],'abstain',text)

    def test_only_document_edge_and_between_clause_whitespace(self):
        r=self.model.read(' '+self.text.replace('。その後、','。\nその後、')+'\n')
        self.assertEqual(r['status'],'read')
        self.assertEqual(self.model.read(self.text.replace('その後、','その後、 '))['status'],'abstain')

    def test_invalid_generation_goals(self):
        for goals in (None,[],['subject'],['subject']*3,['subject',[]],'subject'):
            self.assertEqual(self.model.generate(self.packet,goals)['status'],'abstain')
        for order in (None,[],True,'time_sorted'): self.assertEqual(self.model.generate(self.packet,order=order)['status'],'abstain')

    def test_atomic_second_clause_read_failure(self):
        out=self.model.read('太郎が花子を助けた。その後、彼が健太を褒めた。')
        self.assertEqual(out['status'],'abstain'); self.assertIsNone(out['packet'])

    def test_atomic_second_clause_generation_failure(self):
        with patch.object(self.model.component,'generate',side_effect=[{'status':'generated','text':'first'},{'status':'abstain','reason':'unit'}]):
            out=self.model.generate(self.packet)
        self.assertEqual(out['status'],'abstain'); self.assertIsNone(out['text'])

    def test_unknown_link_abstains_not_time_unknown(self):
        out=self.model.read(self.text.replace('その後、','だから、'))
        self.assertEqual(out['reason'],'unregistered_link_marker')

    def test_temporal_memory_weak_abstains(self):
        fake=SimpleNamespace(recall=lambda _: {'value':None})
        with patch.dict(self.model.memories,{'temporal_read':fake}):
            self.assertEqual(self.model.read(self.text)['reason'],'unlearned_temporal_reading')
        with patch.dict(self.model.memories,{'temporal_write':fake}):
            self.assertEqual(self.model.generate(self.packet)['reason'],'unlearned_temporal_realization')

    def test_reader_full_signal_must_recover(self):
        with patch.object(TemporalModel,'recover',return_value={'status':'abstain'}):
            self.assertEqual(self.model.read(self.text)['reason'],'document_signal_unrecoverable')

    def test_reader_checks_temporal_not_only_events(self):
        m=copy.deepcopy(self.meaning); m['temporal']=copy.deepcopy(TIMES[2])
        with patch.object(TemporalModel,'recover',return_value={'status':'recovered','meaning':m}):
            self.assertEqual(self.model.read(self.text)['reason'],'document_signal_mismatch')

    def test_generation_never_calls_reader_or_feature_training(self):
        with patch.object(TemporalModel,'read',side_effect=AssertionError()),patch.object(ComponentModel,'read',side_effect=AssertionError()),patch('plm_l1_v06.banked.dependency_leaves',side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.packet)['status'],'generated')

    def test_runtime_does_not_use_japanese_link_rules(self):
        root=Path(__file__).resolve().parents[1]/'plm_l1_v08'
        for p in root.glob('*.py'):
            content=p.read_text(encoding='utf-8')
            self.assertNotIn('その後',content); self.assertNotIn('その前',content)

    def test_component_code_and_weights_unchanged(self):
        old=ComponentModel.load(V07/'results'/'model'/'component')
        self.assertEqual(old.fingerprint,self.model.component.fingerprint)
        for name,memory in old.memories.items():
            self.assertEqual([b.blob for b in memory.blocks],[b.blob for b in self.model.component.memories[name].blocks])

    def test_temporal_training_is_pairs_not_operations(self):
        meta=self.model.meta['training']
        self.assertEqual(meta['pair_count'],216); self.assertEqual(meta['supervision'],['text','meaning'])
        self.assertFalse(meta['supplied_operation_traces'])
        self.assertTrue(all(x['complete_contexts']==6 for x in meta['statistics'].values()))

    def test_identity_and_binding_limits_explicit(self):
        self.assertEqual(self.model.meta['binding_and_boundaries'],'designed_not_learned')
        self.assertIn('not_cross_document',self.model.meta['event_identity'])

    def test_inference_always_disabled(self):
        for r in (self.packet,self.model.read(self.text),self.model.recover(self.packet),self.model.generate(self.packet),self.model.read('invalid')):
            self.assertIs(r['eligible_for_inference'],False)

    def test_save_load_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory); m=TemporalModel.load(directory)
            self.assertEqual(m.fingerprint,self.model.fingerprint)
            self.assertEqual(m.generate(self.packet,order='reverse'),self.model.generate(self.packet,order='reverse'))

    def test_no_model_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            with self.assertRaises(ValueError): self.model.save(directory)

    def test_metadata_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory); p=Path(directory)/'model.json'; m=json.loads(p.read_text(encoding='utf-8'))
            m['metadata']['relation']='causal_inference'; p.write_text(json.dumps(m),encoding='utf-8')
            with self.assertRaises(ValueError): TemporalModel.load(directory)

    def test_weights_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory); p=Path(directory)/'weights.npz'
            with np.load(p,allow_pickle=False) as z: weights={k:z[k].copy() for k in z.files}
            weights[next(iter(weights))][-1]^=1; np.savez_compressed(p,**weights)
            with self.assertRaises(ValueError): TemporalModel.load(directory)

    def test_invalid_codec_configuration(self):
        for kwargs in ({'dimension':0},{'dimension':True},{'dimension':192},{'mode':[]},{'seed':''},{'seed':'x'*81}):
            with self.assertRaises(ValueError): TemporalCodec(self.model.codec.candidates,**kwargs)

    def test_training_rejects_trace_and_ambiguous_alignment(self):
        pairs=copy.deepcopy(data('temporal_train')[:1]); pairs[0]['trace']=['gold']
        with self.assertRaises(ValueError): fit(data('component_train'),pairs,data('lexicon'))
        pairs=copy.deepcopy(data('temporal_train')[:1]); pairs[0]['meaning']['events'][0]['subject']=pairs[0]['meaning']['events'][0]['object']
        with self.assertRaises(ValueError): fit(data('component_train'),pairs,data('lexicon'))

    def test_training_conflicting_relations_rejected(self):
        p=copy.deepcopy(data('temporal_train')); extra=copy.deepcopy(p[0]); extra['meaning']['temporal']=copy.deepcopy(TIMES[1]); p.append(extra)
        with self.assertRaises(ValueError): fit(data('component_train'),p,data('lexicon'))

    def test_learning_controls(self):
        results=learning_controls(self.rows)
        for name in ('no_learning','flipped_teacher','renamed_markers','without_after'):
            for r in results[name]['records']:
                self.assertTrue(not r['accepted'] if r['expected_abstain'] else r['exact'],(name,r))

    def test_relation_table_reference_also_succeeds(self):
        results=learning_controls(self.rows)['relation_table_reference']
        self.assertEqual((results['read_keys'],results['write_keys']),(6,6))
        self.assertTrue(all(r['read_exact'] and r['write_exact'] for r in results['records']))

    def test_unordered_event_pair_splits_disjoint(self):
        sets=[]
        for rows in (data('temporal_train'),self.rows,data('evaluation')):
            sets.append({canonical(sorted([{k:v for k,v in e.items() if k!='id'} for e in row['meaning']['events']],key=canonical)) for row in rows})
        self.assertEqual([len(s) for s in sets],[36,36,36])
        self.assertFalse(sets[0]&sets[1] or sets[0]&sets[2] or sets[1]&sets[2])

    def test_new_temporal_training_uses_only_subject_subject(self):
        self.assertTrue(all(parse(row['text'])['goals']==['subject','subject'] for row in data('temporal_train')))
        self.assertEqual({tuple(r['input_goals']) for r in self.rows},set(map(tuple,GOALS)))

    def test_oracle_does_not_ignore_temporal_direction(self):
        self.assertNotEqual(parse(self.text),parse(self.text.replace('その後、','その前に、')))
        self.assertNotEqual(parse(self.text),parse(self.text.replace('その後、','')))

    def test_missing_relation_is_explicit_signal_not_no_signal(self):
        m=copy.deepcopy(self.meaning); m['temporal']=copy.deepcopy(TIMES[0])
        self.assertEqual(self.model.recover(self.model.encode(m))['meaning']['temporal'],TIMES[0])

    def test_valid_altered_relation_is_not_authentication(self):
        m=copy.deepcopy(self.meaning); m['temporal']=copy.deepcopy(TIMES[2])
        out=self.model.generate(self.model.encode(m))
        self.assertEqual(out['status'],'generated'); self.assertIn('その前に、',out['text'])

    def test_count_wrong_and_abstain_separately(self):
        r=[{'stage':'read','accepted':True,'exact':True},{'stage':'read','accepted':True,'exact':False},{'stage':'read','accepted':False,'exact':False}]
        self.assertEqual(count(r)['read'],{'requests':3,'accepted':2,'exact':1,'wrong':1,'abstained':1})

    def test_noise_seed_suffix_changes_direction_reproducibly(self):
        a=noise_rng('temporal-noise-development-0').normal(size=32)
        self.assertTrue(np.array_equal(a,noise_rng('temporal-noise-development-0').normal(size=32)))
        self.assertFalse(np.array_equal(a,noise_rng('temporal-noise-development-1').normal(size=32)))


if __name__=='__main__': unittest.main()
