import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from ss_partial.runtime import PartialModel
from ss_partial.contract import from_meaning,cell
from ss_core_v03.runtime import WaveComponent,WaveDocument
from ss_core_v03.codecs import WaveDocumentCodec,WavePartialCodec
from ss_document.runtime import DocumentModel
from ss_document.codec import DocumentCodec
from plm_l1_v09.component.runtime import Model
from ss_core_v04.runtime import load
from ss_core_v04.memory import WorkingMemory
from ss_core_v04.boundary import controls,teacher,observe,from_observation
from ss_core_v03.waveform import Engine,ArrayPort,PILOT

ROOT=Path(__file__).resolve().parents[1]
TEXT='太郎が花子を助けた。その後、もし次郎が美咲を褒めなかったら。'

class WorkingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old=PartialModel.load(ROOT/'model')
        cls.packet=cls.old.document.read(TEXT)['packet']
        cls.meaning=cls.old.document.recover(cls.packet)['meaning']
        cls.core=load(ROOT)
    def setUp(self):
        self.wm=WorkingMemory.from_document(self.packet,self.core.schema,self.core.engine)

    def test_storage_is_two_superpositions(self):
        self.assertEqual(self.wm.signal.shape,(2,8192))
        self.assertFalse(hasattr(self.wm,'__dict__'))
        self.assertFalse(hasattr(self.wm,'meaning'))

    def test_numeric_role_query(self):
        address,value=teacher(self.core,ROOT,'event:1/subject','entity:次郎')
        np.testing.assert_array_equal(self.wm.value(address),value)

    def test_no_semantic_decoder_or_old_generator(self):
        from contextlib import ExitStack
        with ExitStack() as s:
            for cls,name in ((WaveComponent,'recover'),(WaveDocument,'recover'),(WaveDocumentCodec,'recover'),(WavePartialCodec,'recover'),(DocumentModel,'recover'),(DocumentModel,'generate'),(DocumentCodec,'recover'),(Model,'recover'),(Model,'generate')):
                s.enter_context(patch.object(cls,name,side_effect=AssertionError('legacy semantic path')))
            s.enter_context(patch('ss_core_v04.boundary.observe',side_effect=AssertionError('observer')))
            r=self.core.generate(self.wm,*controls(self.core,'reverse',['object','object']))
        self.assertEqual(r['text'],'もし美咲を次郎が褒めなかったら。その前に、花子を太郎が助けた。')

    def test_local_update_and_other_fields(self):
        before=observe(self.wm,ROOT)
        a,v=teacher(self.core,ROOT,'event:1/subject','entity:花子')
        new,r=self.wm.update(a,v)
        self.assertEqual(r['status'],'updated')
        after=observe(new,ROOT)
        self.assertEqual(after.pop('event:1/subject')['candidates'],['entity:花子'])
        before.pop('event:1/subject');self.assertEqual(before,after)

    def test_zero_meaning_cannot_use_hidden_answer(self):
        self.wm.signal[0]=0
        self.assertEqual(self.core.generate(self.wm,*controls(self.core))['status'],'held')

    def test_zero_status_holds(self):
        self.wm.signal[1]=0
        self.assertEqual(self.core.generate(self.wm,*controls(self.core))['status'],'held')

    def test_extra_candidate_not_silently_dropped(self):
        a,v=teacher(self.core,ROOT,'event:1/subject','entity:花子')
        self.wm.signal[0]+=a*v
        self.assertEqual(self.core.generate(self.wm,*controls(self.core))['status'],'held')

    def test_unknown_address_hold(self):
        bad=np.ones(8192,complex)
        with self.assertRaises(ValueError):self.wm.value(bad)

    def test_domain_mismatch_update_does_not_commit(self):
        a,_=teacher(self.core,ROOT,'event:1/subject','entity:次郎')
        _,v=teacher(self.core,ROOT,'event:0/predicate','predicate:help')
        old=self.wm.fingerprint;new,r=self.wm.update(a,v)
        self.assertEqual(r['status'],'held');self.assertEqual(new.fingerprint,old)

    def test_partial_states_preserved(self):
        for state,values in [('unobserved',[]),('ambiguous',['entity:太郎','entity:花子']),('conflict',['entity:太郎','entity:花子'])]:
            obs=from_meaning(self.meaning,self.old.codec.candidates)
            obs['cells']['event:1/subject']=cell(state,values)
            wm=from_observation(self.core,ROOT,obs)
            c=wm.probe(teacher(self.core,ROOT,'event:1/subject','entity:次郎')[0])
            self.assertEqual(c.count,len(values));self.assertFalse(c.ready)
            self.assertEqual(self.core.generate(wm,*controls(self.core))['status'],'held')

    def test_teacher_resolves_partial(self):
        obs=from_meaning(self.meaning,self.old.codec.candidates)
        obs['cells']['event:1/subject']=cell('ambiguous',['entity:太郎','entity:花子'])
        wm=from_observation(self.core,ROOT,obs)
        new,r=wm.update(*teacher(self.core,ROOT,'event:1/subject','entity:次郎'))
        self.assertEqual(r['status'],'updated')
        self.assertTrue(new.validate(True)['complete'])

    def test_save_load_only_numeric_memory(self):
        with tempfile.TemporaryDirectory() as d:
            self.wm.save(Path(d)/'wm')
            other=WorkingMemory.load(Path(d)/'wm',self.core.schema,self.core.engine)
            with np.load(Path(d)/'wm/signal.npz',allow_pickle=False) as f:self.assertEqual(f.files,['signal'])
            self.assertEqual(other.fingerprint,self.wm.fingerprint)

    def test_corrupt_save_detected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'wm';self.wm.save(path)
            a=self.wm.signal.copy();a[0,0]+=1;np.savez_compressed(path/'signal.npz',signal=a)
            with self.assertRaisesRegex(ValueError,'wm_hash'):WorkingMemory.load(path,self.core.schema,self.core.engine)

    def test_terminal_only_label_boundary(self):
        self.assertFalse(hasattr(self.core.schema,'value_labels'))
        self.assertFalse(hasattr(self.core.schema,'address_names'))
        self.assertTrue(all(isinstance(v,str) for v in self.core.terminal.surfaces))

    def test_bad_frame_never_generates(self):
        def port(source,pilots,tag):
            for tick,y,mask in ArrayPort(source,pilots,tag):
                if tick==source.shape[1]+2*PILOT-1:return
                yield tick,y,mask
        c=load(ROOT,Engine(port));wm=WorkingMemory(self.wm.signal,c.schema,c.engine)
        self.assertEqual(c.generate(wm,*controls(c))['status'],'held')

    def test_learned_map_zero_disables_generation(self):
        m=self.core.maps['lexical'];saved=m.weights.copy()
        try:
            m.weights[:]=0
            self.assertEqual(self.core.generate(self.wm,*controls(self.core))['status'],'held')
        finally:m.weights[:]=saved

    def test_nonfinite_packet(self):
        p=copy.deepcopy(self.packet);p['imag'][0]=float('nan')
        with self.assertRaises(ValueError):WorkingMemory.from_document(p,self.core.schema,self.core.engine)

    def test_rejected_correction_no_stale_text(self):
        a,_=teacher(self.core,ROOT,'event:1/subject','entity:次郎')
        _,v=teacher(self.core,ROOT,'event:0/predicate','predicate:help')
        new,r=self.core.revise_and_generate(self.wm,a,v,*controls(self.core))
        self.assertEqual(r['status'],'held');self.assertIsNone(r['text'])
        self.assertEqual(new.fingerprint,self.wm.fingerprint)

    def test_malformed_presentation_rejected(self):
        obs=from_meaning(self.meaning,self.old.codec.candidates);obs['presentation']=['event:0','event:0']
        with self.assertRaisesRegex(ValueError,'presentation'):from_observation(self.core,ROOT,obs)

    def test_malformed_control_rejected(self):
        r=self.core.generate(self.wm,np.ones(1),np.ones((2,8192)))
        self.assertEqual(r['status'],'held');self.assertEqual(r['reason'],'order_signal')

if __name__=='__main__':unittest.main()
