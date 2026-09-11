import copy
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np
from ss_document.runtime import DocumentModel,PACKET_FIELDS
from ss_document.training import train,variant
from ss_document.contract import normalize,edge,IDS
from evaluation.integrity import ROOT,read
from evaluation.oracle import render,parse,localize
from evaluation.cases import corpus,scene_key,INVALID

TEXT='太郎が花子を助けた。その後、花子が健太を褒めた。その前に、健太が由紀を訪ねた。'


class DocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=train(read(ROOT/'data/component_train.json'),read(ROOT/'data/temporal_train.json'),read(ROOT/'data/lexicon.json'),seed='unit-doc')
        cls.base=cls.model.base
        cls.result=cls.model.read(TEXT)
        assert cls.result['status']=='read',cls.result
        cls.meaning=cls.model.recover(cls.result['packet'])['meaning']

    def test_three_event_roundtrip_reverse(self):
        out=self.model.generate(self.result['packet'],'reverse',['subject']*3)
        self.assertEqual(out['status'],'generated')
        self.assertEqual(out['text'],'健太が由紀を訪ねた。その後、花子が健太を褒めた。その前に、太郎が花子を助けた。')
        self.assertEqual(out['event_order'],list(reversed(IDS)))

    def test_all_adjacent_link_combinations(self):
        for n in (2,3):
            sample=next(r['meaning'] for r in corpus('unit-links',1) if len(r['meaning']['events'])==n)
            for options in itertools.product((0,1,2),repeat=n-1):
                m=copy.deepcopy(sample)
                for i,opt in enumerate(options):
                    a,b=IDS[i:i+2];m['relations'][next(j for j,r in enumerate(m['relations']) if r['pair']==[a,b])]=edge(a,b) if opt==0 else edge(a,b,a,b) if opt==1 else edge(a,b,b,a)
                p=self.model.encode(m);rec=self.model.recover(p);self.assertEqual(rec['meaning'],m)
                for reverse in (False,True):
                    g=['object']*n;out=self.model.generate(p,'reverse' if reverse else 'preserve',g)
                    self.assertEqual(out['text'],render(m,g,reverse))

    def test_packet_has_only_numeric_carrier(self):
        self.assertEqual(set(self.result['packet']),PACKET_FIELDS)
        self.assertNotIn('events',self.result['packet']);self.assertNotIn('count',self.result['packet'])
        self.assertEqual(len(self.result['packet']['real']),8192)

    def test_no_text_or_meaning_hint_accepted(self):
        for key,value in [('text',TEXT),('meaning',self.meaning),('presentation',list(IDS)),('count',3)]:
            self.assertEqual(self.model.recover(self.result['packet']|{key:value})['status'],'abstain')

    def test_model_mismatch(self):
        other=DocumentModel(self.base,seed='unit-other')
        self.assertEqual(other.generate(self.result['packet'])['status'],'abstain')

    def test_zero_and_nan_and_bool(self):
        for value in (0.,float('nan'),True):
            p=copy.deepcopy(self.result['packet']);p['real']=[value]*8192
            if value==0.:p['imag']=[0.]*8192
            self.assertEqual(self.model.recover(p)['status'],'abstain')

    def test_bad_numeric_shape(self):
        p=copy.deepcopy(self.result['packet']);p['real']=p['real'][:-1]
        self.assertEqual(self.model.recover(p)['status'],'abstain')

    def test_missing_event_rejected(self):
        c=self.model.codec;v=c.encode(self.meaning);i=2
        lost=c.presence[i].copy()
        for r in c.candidates:lost+=c.events[i][r][c.candidates[r].index(self.meaning['events'][i][r])]
        self.assertEqual(self.model.recover(self.model.packet(v-lost/math.sqrt(3)))['status'],'abstain')

    def test_signal_slot_edit_is_local(self):
        c=self.model.codec;m=copy.deepcopy(self.meaning);v=c.encode(m);old=m['events'][1]['subject'];new='entity:次郎'
        v+=(c.events[1]['subject'][c.candidates['subject'].index(new)]-c.events[1]['subject'][c.candidates['subject'].index(old)])/math.sqrt(3)
        m['events'][1]['subject']=new;rec=self.model.recover(self.model.packet(v));self.assertEqual(rec['meaning'],m)

    def test_signal_edge_edit_is_local(self):
        c=self.model.codec;m=copy.deepcopy(self.meaning);v=c.encode(m);r=m['relations'][0];pair=tuple(r['pair']);i=c.relation_values[pair].index(r)
        j=3-i;v+=(c.relations[pair][j]-c.relations[pair][i])/math.sqrt(3);m['relations'][0]=c.relation_values[pair][j]
        self.assertEqual(self.model.recover(self.model.packet(v))['meaning'],m)

    def test_unknown_relation_not_inferred(self):
        m=self.model.recover(self.result['packet'])['meaning']
        self.assertEqual(m['relations'][1]['kind'],'unknown')

    def test_nonadjacent_explicit_relation_refused(self):
        m=copy.deepcopy(self.meaning);m['relations'][1]=edge(IDS[0],IDS[2],IDS[0],IDS[2])
        with self.assertRaises(ValueError):self.model.encode(m)

    def test_bad_counts_and_identity(self):
        for n in (1,4):
            m=copy.deepcopy(self.meaning);m['events']=(m['events']*2)[:n]
            with self.assertRaises(ValueError):self.model.encode(m)
        m=copy.deepcopy(self.meaning);m['events'][1]['id']=IDS[0]
        with self.assertRaises(ValueError):self.model.encode(m)

    def test_duplicate_pair_and_bad_endpoint(self):
        m=copy.deepcopy(self.meaning);m['relations'][1]=m['relations'][0]
        with self.assertRaises(ValueError):self.model.encode(m)
        m=copy.deepcopy(self.meaning);m['relations'][0]['target']='event:9'
        with self.assertRaises(ValueError):self.model.encode(m)

    def test_unsupported_inputs_abstain_whole_document(self):
        for text in INVALID:
            out=self.model.read(text);self.assertEqual(out['status'],'abstain',text)
            self.assertIsNone(out['text']);self.assertIsNone(out['packet'])

    def test_repeated_occurrences_not_deduplicated(self):
        t='太郎が花子を助けた。その後、太郎が花子を助けた。その後、太郎が花子を助けた。'
        out=self.model.read(t);self.assertEqual(out['status'],'read')
        m=self.model.recover(out['packet'])['meaning'];self.assertEqual(len(m['events']),3)
        self.assertEqual(self.model.generate(out['packet'])['text'],t)

    def test_negation_hypothesis_and_object_order(self):
        t='もし花子を太郎が助けなかったら。その前に、健太を由紀が褒めた。'
        out=self.model.read(t);self.assertEqual(out['status'],'read')
        generated=self.model.generate(out['packet'],'preserve',['object','object'])
        self.assertEqual(generated['text'],t)

    def test_unbound_occurrence_collision(self):
        model=DocumentModel(self.base,mode='unbound_events');m=copy.deepcopy(self.meaning);other=copy.deepcopy(m)
        for role in model.codec.candidates:other['events'][0][role],other['events'][1][role]=other['events'][1][role],other['events'][0][role]
        np.testing.assert_allclose(model.codec.encode(m),model.codec.encode(other),rtol=0,atol=3e-15)
        self.assertFalse(np.allclose(self.model.codec.encode(m),self.model.codec.encode(other)))

    def test_undirected_time_collision(self):
        model=DocumentModel(self.base,mode='undirected_time');m=copy.deepcopy(self.meaning);other=copy.deepcopy(m)
        other['relations'][0]['source'],other['relations'][0]['target']=other['relations'][0]['target'],other['relations'][0]['source']
        np.testing.assert_array_equal(model.codec.encode(m),model.codec.encode(other))
        self.assertEqual(model.recover(model.encode(m))['status'],'abstain')

    def test_zero_temporal_read(self):
        model=variant(self.base,condition='zero_temporal_read');self.assertEqual(model.read(TEXT)['status'],'abstain')

    def test_zero_temporal_write(self):
        model=variant(self.base,condition='zero_temporal_write');p=model.encode(self.meaning)
        self.assertEqual(model.recover(p)['status'],'recovered');self.assertEqual(model.generate(p)['status'],'abstain')

    def test_zero_lexical_write(self):
        model=variant(self.base,condition='zero_lexical_write');self.assertEqual(model.generate(model.encode(self.meaning))['status'],'abstain')

    def test_bad_generation_goals(self):
        for order,goals in [('shuffle',None),('preserve',['subject']),('preserve',['subject','object','topic'])]:
            self.assertEqual(self.model.generate(self.result['packet'],order,goals)['status'],'abstain')

    def test_save_load_and_fresh_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'model';self.model.save(p);m=DocumentModel.load(p)
            self.assertEqual(m.fingerprint,self.model.fingerprint)
            self.assertEqual(m.generate(self.result['packet'])['text'],self.model.generate(self.result['packet'])['text'])
            with self.assertRaises(FileExistsError):self.model.save(p)

    def test_cache_clearing_does_not_change_generation(self):
        before=self.model.generate(self.result['packet'])
        for memory in list(self.base.memories.values())+list(self.base.component.memories.values()):memory.clear_cache()
        self.assertEqual(before,self.model.generate(self.result['packet']))

    def test_development_no_three_event_training(self):
        trainrows=read(ROOT/'data/temporal_train.json');self.assertTrue(all(len(r['meaning']['events'])==2 for r in trainrows))
        dev=corpus('development',4);self.assertEqual(len(dev),48)
        self.assertFalse({scene_key(r['meaning']['events']) for r in dev}&{scene_key(r['meaning']['events']) for r in trainrows})


if __name__=='__main__':unittest.main()
