import copy
import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT, read
from evaluation.oracle import parse
from plm_l1_v09.component.algebra import digest
from ss_document.runtime import DocumentModel, PACKET_FIELDS
from ss_partial.runtime import PartialModel
from ss_partial.contract import cell, from_meaning, to_meaning, normalize, inventory
from ss_partial.reader import read as read_text
from ss_partial.update import apply, request

TEXT = '太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が美咲を訪ねた。'
ALTERNATIVE = '太郎が花子を助けた。その後、由紀が健太を褒めた。その後、健太が美咲を訪ねた。'
TARGET = 'event:1/subject'


class PartialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = DocumentModel.load(ROOT / 'model/document')
        cls.model = PartialModel(cls.document)
        out = cls.document.read(TEXT)
        assert out['status'] == 'read'
        cls.meaning = cls.document.recover(out['packet'])['meaning']
        cls.known = from_meaning(cls.meaning, cls.model.codec.candidates)

    def observation(self, state='ambiguous', values=None, target=TARGET):
        o = copy.deepcopy(self.known)
        if values is None:
            values = ['entity:花子', 'entity:由紀'] if state in ('ambiguous', 'conflict') else []
        o['cells'][target] = cell(state, values)
        return normalize(o, self.model.codec.candidates)

    def test_known_roundtrip(self):
        self.assertEqual(self.model.recover(self.model.encode(self.known))['observation'], self.known)

    def test_known_generation(self):
        self.assertEqual(self.model.generate(self.model.encode(self.known))['text'], TEXT)

    def test_all_states_roundtrip(self):
        for state in ('ambiguous', 'unobserved', 'unreadable', 'conflict'):
            o = self.observation(state)
            self.assertEqual(self.model.recover(self.model.encode(o))['observation'], o)

    def test_no_text_until_resolved(self):
        for state in ('ambiguous', 'unobserved', 'unreadable', 'conflict'):
            out = self.model.generate(self.model.encode(self.observation(state)))
            self.assertEqual(out['status'], 'needs_information')
            self.assertNotIn('text', out)

    def test_localizes_target_and_keeps_both_candidates(self):
        out = self.model.inspect(self.model.encode(self.observation()))
        self.assertEqual(out['requests'], [{'target': TARGET, 'state': 'ambiguous', 'candidates': ['entity:花子', 'entity:由紀']}])

    def test_missing_and_unreadable_signals_differ(self):
        a = self.model.encode(self.observation('unobserved'))
        b = self.model.encode(self.observation('unreadable'))
        self.assertNotEqual(digest(a), digest(b))
        self.assertEqual(self.model.inspect(a)['requests'][0]['state'], 'unobserved')
        self.assertEqual(self.model.inspect(b)['requests'][0]['state'], 'unreadable')

    def test_known_unspecified_time_does_not_request(self):
        o = copy.deepcopy(self.known)
        o['cells']['time/event:0,event:1'] = cell('known', ['unspecified'])
        self.assertEqual(self.model.inspect(self.model.encode(o))['status'], 'ready')

    def test_ambiguous_time_does_request(self):
        o = self.observation('ambiguous', ['before', 'after'], 'time/event:0,event:1')
        self.assertEqual(self.model.inspect(self.model.encode(o))['requests'][0]['target'], 'time/event:0,event:1')

    def test_supply_each_uncertain_state(self):
        for state in ('ambiguous', 'unobserved', 'unreadable'):
            p = self.model.encode(self.observation(state))
            out = apply(self.model, p, request(p, TARGET, 'entity:由紀'))
            self.assertEqual(out['status'], 'updated')
            self.assertEqual(self.model.generate(out['packet'])['text'], ALTERNATIVE)

    def test_numeric_delta_and_non_target_hold(self):
        o = self.observation(); p = self.model.encode(o); before = copy.deepcopy(p)
        out = apply(self.model, p, request(p, TARGET, 'entity:由紀'))
        target = cell('known', ['entity:由紀'])
        expected = self.model.vector(p) + (self.model.codec.cell_vector(TARGET, target) - self.model.codec.cell_vector(TARGET, o['cells'][TARGET])) / math.sqrt(3.)
        np.testing.assert_array_equal(self.model.vector(out['packet']), expected)
        actual = self.model.recover(out['packet'])['observation']
        self.assertTrue(all(v == actual['cells'][k] for k, v in o['cells'].items() if k != TARGET))
        self.assertEqual(p, before)

    def test_preserves_small_carrier_noise_instead_of_reencoding(self):
        o = self.observation(); p = self.model.encode(o)
        noise = np.random.default_rng(12).normal(0, 0.005, self.model.codec.dimension).astype(complex)
        p = self.model.packet(self.model.vector(p) + noise)
        out = apply(self.model, p, request(p, TARGET, 'entity:由紀'))
        self.assertEqual(out['status'], 'updated')
        clean = self.model.codec.encode(self.model.recover(out['packet'])['observation'])
        np.testing.assert_allclose(self.model.vector(out['packet']) - clean, noise, atol=1e-14, rtol=1e-10)

    def test_outside_candidate_is_conflict(self):
        p = self.model.encode(self.observation())
        out = apply(self.model, p, request(p, TARGET, 'entity:次郎'))
        self.assertEqual(out['status'], 'conflict')
        self.assertEqual(len(self.model.recover(out['packet'])['observation']['cells'][TARGET]['candidates']), 3)
        self.assertEqual(self.model.generate(out['packet'])['status'], 'needs_information')

    def test_disagreeing_known_value_is_conflict(self):
        p = self.model.encode(self.known)
        self.assertEqual(apply(self.model, p, request(p, TARGET, 'entity:由紀'))['status'], 'conflict')

    def test_supply_does_not_implicitly_resolve_conflict(self):
        p = self.model.encode(self.observation('conflict'))
        out = apply(self.model, p, request(p, TARGET, 'entity:由紀'))
        self.assertEqual(self.model.generate(out['packet'])['status'], 'needs_information')

    def test_explicit_conflict_resolution(self):
        p = self.model.encode(self.observation('conflict'))
        out = apply(self.model, p, request(p, TARGET, 'entity:由紀', 'resolve'))
        self.assertEqual(self.model.generate(out['packet'])['text'], ALTERNATIVE)

    def test_resolution_cannot_introduce_new_candidate(self):
        p = self.model.encode(self.observation('conflict'))
        self.assertEqual(apply(self.model, p, request(p, TARGET, 'entity:次郎', 'resolve'))['status'], 'rejected')

    def test_explicit_known_revision(self):
        p = self.model.encode(self.known)
        out = apply(self.model, p, request(p, TARGET, 'entity:由紀', 'revise'))
        self.assertEqual(self.model.generate(out['packet'])['text'], ALTERNATIVE)

    def test_stale_request_rejected(self):
        p = self.model.encode(self.observation()); msg = request(p, TARGET, 'entity:由紀')
        out = apply(self.model, p, msg)
        self.assertEqual(apply(self.model, out['packet'], msg)['reason'], 'stale_or_wrong_document')

    def test_wrong_document_request_rejected(self):
        p = self.model.encode(self.observation()); other = self.model.encode(self.known)
        self.assertEqual(apply(self.model, other, request(p, TARGET, 'entity:由紀'))['status'], 'rejected')

    def test_matching_teacher_idempotent(self):
        p = self.model.encode(self.known)
        out = apply(self.model, p, request(p, TARGET, 'entity:花子'))
        self.assertEqual(out['status'], 'unchanged')
        self.assertEqual(out['packet'], p)

    def test_malformed_update_atomic(self):
        p = self.model.encode(self.observation()); original = copy.deepcopy(p)
        for change in ({'target': 'event:9/subject'}, {'value': 'entity:未知'}, {'operation': 'guess'}, {'text': TEXT}):
            out = apply(self.model, p, request(p, TARGET, 'entity:由紀') | change)
            self.assertEqual(out['status'], 'rejected'); self.assertNotIn('packet', out); self.assertEqual(p, original)

    def test_packet_has_no_side_channel(self):
        p = self.model.encode(self.observation())
        self.assertEqual(set(p), PACKET_FIELDS)
        for k in ('observation', 'meaning', 'target', 'candidates', 'text', 'count'):
            self.assertEqual(self.model.recover(p | {k: 1})['status'], 'abstain')

    def test_zero_nan_bool_truncated_signals(self):
        p = self.model.encode(self.observation())
        for value in (0., float('nan'), True):
            q = copy.deepcopy(p); q['real'] = [value] * 8192; q['imag'] = [value] * 8192
            self.assertEqual(self.model.recover(q)['status'], 'abstain')
        self.assertEqual(self.model.recover(p | {'real': p['real'][:-1]})['status'], 'abstain')

    def test_candidate_erasure_is_not_semantic_unobserved(self):
        p = self.model.encode(self.known)
        v = self.model.vector(p) - self.model.codec.values[TARGET][self.model.codec.choices[TARGET].index('entity:花子')] / math.sqrt(3.)
        self.assertEqual(self.model.recover(self.model.packet(v))['status'], 'abstain')

    def test_extra_candidate_cannot_be_silently_dropped(self):
        p = self.model.encode(self.known)
        v = self.model.vector(p) + self.model.codec.values[TARGET][self.model.codec.choices[TARGET].index('entity:由紀')] / math.sqrt(3.)
        self.assertEqual(self.model.recover(self.model.packet(v))['status'], 'abstain')

    def test_bad_state_cardinality(self):
        for state, values in (('known', []), ('known', ['entity:花子', 'entity:由紀']), ('ambiguous', ['entity:花子']), ('unreadable', ['entity:花子']), ('conflict', [])):
            with self.assertRaises(ValueError): self.model.encode(self.observation(state, values))

    def test_nonadjacent_relation_rejected(self):
        with self.assertRaises(ValueError):
            self.model.encode(self.observation('ambiguous', ['before', 'after'], 'time/event:0,event:2'))

    def test_duplicate_candidate_rejected(self):
        with self.assertRaises(ValueError): self.observation('ambiguous', ['entity:花子', 'entity:花子'])

    def test_multiple_unresolved_fields(self):
        o = self.observation(); o['cells']['event:2/polarity'] = cell('unreadable', [])
        p = self.model.encode(o)
        out = apply(self.model, p, request(p, TARGET, 'entity:由紀'))
        self.assertEqual(self.model.inspect(out['packet'])['requests'], [{'target': 'event:2/polarity', 'state': 'unreadable', 'candidates': []}])
        self.assertEqual(self.model.generate(out['packet'])['status'], 'needs_information')

    def test_all_roles_and_adjacent_time_can_be_completed(self):
        for target, choices in inventory(3, self.model.codec.candidates).items():
            if target == 'time/event:0,event:2': continue
            o = copy.deepcopy(self.known); o['cells'][target] = cell('unobserved', [])
            p = self.model.encode(o)
            out = apply(self.model, p, request(p, target, self.known['cells'][target]['candidates'][0]))
            self.assertEqual(self.model.recover(out['packet'])['observation'], self.known)

    def test_two_explicit_readings(self):
        result = read_text(self.model, [TEXT, ALTERNATIVE])
        self.assertEqual(result['status'], 'read')
        self.assertEqual(self.model.recover(result['packet'])['observation'], self.observation())

    def test_complete_reader_unchanged(self):
        result = read_text(self.model, [TEXT])
        self.assertEqual(self.model.generate(result['packet'])['text'], TEXT)

    def test_multiple_difference_readings_rejected(self):
        result = read_text(self.model, [TEXT, ALTERNATIVE.replace('褒めた', '褒めなかった')])
        self.assertEqual(result['status'], 'abstain')

    def test_repeated_occurrences_not_merged(self):
        result = read_text(self.model, ['太郎が花子を助けた。太郎が花子を助けた。'])
        self.assertEqual(result['status'], 'read')
        self.assertEqual(self.model.generate(result['packet'])['text'].count('太郎が花子を助けた。'), 2)

    def test_save_load(self):
        with tempfile.TemporaryDirectory(prefix='ssdoc02-unit-') as temp:
            path = Path(temp) / 'model'; self.model.save(path); other = PartialModel.load(path)
            self.assertEqual(other.fingerprint, self.model.fingerprint)
            self.assertEqual(other.inspect(self.model.encode(self.observation()))['requests'][0]['target'], TARGET)

    def test_no_long_term_learning(self):
        before = self.document.fingerprint
        p = self.model.encode(self.observation()); apply(self.model, p, request(p, TARGET, 'entity:由紀'))
        self.assertEqual(self.model.document.fingerprint, before)
        self.assertEqual(self.model.generate(p)['status'], 'needs_information')

    def test_status_ablation_fails_closed(self):
        other = PartialModel(self.document, mode='drop_state')
        self.assertEqual(other.recover(other.encode(self.observation()))['status'], 'abstain')

    def test_unbound_ablation_fails_closed(self):
        other = PartialModel(self.document, mode='unbound_events')
        self.assertEqual(other.recover(other.encode(self.observation()))['status'], 'abstain')

    def test_model_fingerprint_mismatch(self):
        p = self.model.encode(self.observation())
        self.assertEqual(self.model.recover(p | {'model_fingerprint': 'other'})['status'], 'abstain')

    def test_complete_reverse_reparse(self):
        out = self.model.generate(self.model.encode(self.known), 'reverse', ['object'] * 3)
        parsed = parse(out['text'])
        self.assertEqual(parsed['relations'][0]['relation'], 'after')
        self.assertEqual(parsed['events'][0]['subject'], 'entity:健太')

    def test_evaluation_scene_disjointness_and_count(self):
        from evaluation.cases import scenes, cases, scene_key
        dev, final = scenes('development'), scenes('evaluation')
        forbidden = {scene_key(s['meaning']['events']) for s in dev + read(ROOT / 'data/doc_v01_regression.json') + read(ROOT / 'data/temporal_train.json')}
        self.assertFalse(forbidden & {scene_key(s['meaning']['events']) for s in final})
        self.assertEqual(len(final), 8)
        self.assertEqual(len(cases('evaluation')), 336)


if __name__ == '__main__': unittest.main()
