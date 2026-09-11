import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from plm_l1_v09.component.runtime import Model
from plm_l1_v09.component.banked import MemoryBlock, BankedMemory
from ss_document.runtime import DocumentModel
from ss_document.codec import DocumentCodec
from ss_partial.codec import PartialCodec
from ss_partial.runtime import PartialModel
from ss_partial.contract import from_meaning, cell
from ss_core_v03.waveform import Engine, Receiver, ArrayPort, PILOT
from ss_core_v03.runtime import load, run_text
from ss_core_v03.program import Program
from ss_core_v03.banked import WaveMemory
from ss_core_v03.correction import UnifiedCorrection
from ss_core.memory import WaveCorrectionView
from ss_retention.memory import CorrectionMemory
from ss_core.learning import learn
from plm_l1_v09.component.algebra import digest

ROOT = Path(__file__).resolve().parents[1]
TEXT = '太郎が花子を助けた。その後、もし次郎が美咲を褒めなかったら。'
EXPECTED = 'もし美咲を次郎が褒めなかったら。その前に、花子を太郎が助けた。'

class ReceiverTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.source = rng.normal(size=(2, 128))+1j*rng.normal(size=(2, 128))
        self.basis = np.exp(1j*rng.normal(size=(2, 4, 128)))

    def test_numeric_reference(self):
        actual = Engine().correlate(self.source, self.basis, 'unit')
        expected = (self.basis.conj()*self.source[:, None, :]).sum(axis=2).real/128
        np.testing.assert_allclose(actual, expected, atol=1e-12)

    def test_phase_sync(self):
        def port(source, pilots, tag):
            for tick, y, mask in ArrayPort(source, pilots, tag):
                yield tick, y*np.exp(1j*np.array([.71, -1.1])), mask
        np.testing.assert_allclose(Engine(port).correlate(self.source, self.basis, 'unit'), Engine().correlate(self.source, self.basis, 'unit'), atol=1e-12)

    def test_no_source_in_receiver(self):
        r = Receiver(self.basis, np.ones_like(self.source), np.ones((2, 2, PILOT), complex))
        self.assertFalse(hasattr(r, 'source'))
        self.assertFalse(r.peek()['eligible_for_decision'])
        self.assertIsNone(r.finish()[0])

    def test_truncated_tail(self):
        def port(source, pilots, tag):
            for tick, y, mask in ArrayPort(source, pilots, tag):
                if tick == source.shape[1]+2*PILOT-1:
                    return
                yield tick, y, mask
        with self.assertRaisesRegex(ValueError, 'incomplete_window'):
            Engine(port).correlate(self.source, self.basis, 'unit')

    def test_reorder(self):
        def port(source, pilots, tag):
            for tick, y, mask in ArrayPort(source, pilots, tag):
                yield tick+1 if tick == PILOT else tick, y, mask
        with self.assertRaisesRegex(ValueError, 'tick_order'):
            Engine(port).correlate(self.source, self.basis, 'unit')

    def test_missing_payload(self):
        def port(source, pilots, tag):
            for tick, y, mask in ArrayPort(source, pilots, tag):
                if tick == PILOT:
                    y[:] = 0; mask[:] = False
                yield tick, y, mask
        with self.assertRaisesRegex(ValueError, 'insufficient_payload'):
            Engine(port).correlate(self.source, self.basis, 'unit')

    def test_nonfinite(self):
        self.source[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'wave_finite'):
            Engine().correlate(self.source, self.basis, 'unit')

    def test_source_mutation(self):
        def port(source, pilots, tag):
            for tick, y, mask in ArrayPort(source, pilots, tag):
                if tick == PILOT:
                    source[0, 0] += 1
                yield tick, y, mask
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            Engine(port).correlate(self.source, self.basis, 'unit')

    def test_tail_phase_drift(self):
        def port(source, pilots, tag):
            for tick, y, mask in ArrayPort(source, pilots, tag):
                yield tick, y*(np.exp(.5j) if tick >= PILOT+source.shape[1] else 1), mask
        with self.assertRaisesRegex(ValueError, 'tail_pilot'):
            Engine(port).correlate(self.source, self.basis, 'unit')

    def test_decision_only_after_tail_and_no_second_close(self):
        pilots = np.ones((2, 2, PILOT), complex)
        r = Receiver(self.basis, np.ones_like(self.source), pilots)
        for tick, y, mask in ArrayPort(self.source, pilots, 'unit'):
            r.push(tick, y, mask)
            self.assertFalse(r.peek()['eligible_for_decision'])
        self.assertIsNotNone(r.finish()[0])
        self.assertIsNone(r.finish()[0])

class Integration03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = PartialModel.load(ROOT/'model')
        cls.model = load(ROOT)
        cls.packet = cls.legacy.document.read(TEXT)['packet']

    def test_complete_read_and_generate_without_legacy_scorers(self):
        with patch.object(MemoryBlock, 'recall', side_effect=AssertionError('old block recall')), patch.object(BankedMemory, 'recall', side_effect=AssertionError('old answer cache')), patch.object(Model, 'recover', side_effect=AssertionError('old semantic decoder')), patch.object(DocumentCodec, 'recover', side_effect=AssertionError('old document decoder')):
            out = run_text(self.model, TEXT, 'reverse', ['object', 'object'])
        self.assertEqual(out['text'], EXPECTED)
        self.assertEqual(out['cost']['held_windows'], 0)

    def test_generator_does_not_use_old_order_gap_or_generators(self):
        c = self.model.document.base.component
        with patch.object(c, 'order', side_effect=AssertionError('old order loop')), patch.object(c, 'gap', side_effect=AssertionError('old gap assembly')), patch.object(Model, 'generate', side_effect=AssertionError('old component generation')), patch.object(DocumentModel, 'generate', side_effect=AssertionError('old document generation')):
            out = self.model.document.generate(self.packet, 'reverse', ['object', 'object'])
        self.assertEqual(out['text'], EXPECTED)

    def test_bank_decisions_and_scores_match(self):
        old = self.legacy.document.base.component.memories['lexical_read']
        wave = WaveMemory(old, Engine(), 'lexical_read')
        for surface in ('太郎', '花子', '助け', '未知'):
            a, b = old.recall({'surface': surface}), wave.recall({'surface': surface})
            self.assertEqual(a['value'], b['value'])
            for p, q in zip(a['projections'], b['projections']):
                self.assertAlmostEqual(p['score'], q['score'], places=7)

    def test_repeated_query_does_acquire_new_samples(self):
        wave = self.model.document.base.component.memories['lexical_write']
        context = {'meaning_value': 'entity:太郎'}
        a = len(self.model.engine.trace)
        wave.recall(context)
        b = len(self.model.engine.trace)
        wave.recall(context)
        c = len(self.model.engine.trace)
        self.assertEqual(b-a, c-b)
        self.assertGreater(c-b, 0)
        self.assertNotEqual(self.model.engine.trace[a]['received_sha256'], self.model.engine.trace[b]['received_sha256'])

    def test_partial_wave_decoder_and_hold(self):
        meaning = self.legacy.document.recover(self.packet)['meaning']
        obs = from_meaning(meaning, self.model.codec.candidates)
        obs['cells']['event:1/subject'] = cell('unobserved', [])
        packet = self.model.encode(obs)
        with patch.object(PartialCodec, 'recover', side_effect=AssertionError('old partial decoder')):
            self.assertEqual(self.model.recover(packet)['observation'], obs)
            self.assertEqual(self.model.generate(packet)['status'], 'needs_information')

    def test_program_zero_action_abstains(self):
        p = self.model.document.base.component.program
        weights = p.weights.copy()
        try:
            p.weights[0] = 0
            self.assertEqual(self.model.document.generate(self.packet)['status'], 'abstain')
        finally:
            p.weights[:] = weights

    def test_program_zero_state_abstains(self):
        p = self.model.document.program
        weights = p.weights.copy()
        try:
            p.weights[1] = 0
            r = self.model.document.generate(self.packet)
            self.assertEqual(r['status'], 'abstain')
            self.assertIn('next_state', r['reason'])
        finally:
            p.weights[:] = weights

    def test_program_save_load_signal_state(self):
        p = self.model.document.program
        with tempfile.TemporaryDirectory() as d:
            p.save(Path(d)/'program')
            q = Program.load(Path(d)/'program', Engine())
            a = p.step({'presentation': ['event:0', 'event:1'], 'order': 'reverse'}, p.start())
            b = q.step({'presentation': ['event:0', 'event:1'], 'order': 'reverse'}, q.start())
        self.assertEqual(a[0], b[0])
        self.assertIsInstance(b[1], np.ndarray)
        np.testing.assert_array_equal(a[1], b[1])

    def test_correction_same_receiver_same_decision(self):
        memory = CorrectionMemory(self.model.codec.candidates)
        key = digest('wave03-test')
        self.assertEqual(learn(memory, {'key': key, 'domain': 'subject', 'value': 'entity:太郎', 'protect': True})['status'], 'learned')
        a = WaveCorrectionView(memory).recall(key, 'subject')
        b = UnifiedCorrection(memory, Engine()).recall(key, 'subject')
        self.assertEqual(a['value'], b['value'])
        self.assertEqual(a['status'], b['status'])

    def test_unknown_word_rejected(self):
        out = run_text(self.model, TEXT.replace('太郎', '未知'))
        self.assertEqual(out['status'], 'abstain')

    def test_bad_packet_rejected(self):
        packet = copy.deepcopy(self.packet)
        packet['real'][0] = float('nan')
        self.assertEqual(self.model.document.generate(packet)['status'], 'abstain')

    def test_trace_has_action_and_stop(self):
        r = self.model.document.generate(self.packet)
        self.assertEqual(r['program_audit'][-1]['action'], 'stop')
        self.assertEqual(r['program_audit'][0]['sentence'][-1]['action'], 'stop')

if __name__ == '__main__':
    unittest.main()
