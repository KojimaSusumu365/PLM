import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from plm_l1_v011.algebra import canonical
from plm_l1_v011.core import Model
from plm_l1_v012.core import GuardedModel, POLICIES
from plm_l1_v012.evidence import build_evidence
from plm_l1_v012.training import attach, train_model


def teachers(kind='and'):
    return [{'context': {'a': str(a), 'b': str(b)},
             'label': str((a & b) if kind == 'and' else (a ^ b))}
            for a, b in itertools.product((0, 1), repeat=2)]


def model(backend='ss', kind='and', **kwargs):
    rows = teachers(kind)
    return train_model(rows, rows, rows, backend=backend, selector='off',
                       dimension=512, seed='unit-v012', **kwargs)[0]


class SufficiencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ss = model()
        cls.exact = model('exact')

    def test_01_complete_input_unchanged(self):
        for m in (self.ss, self.exact):
            for row in teachers():
                self.assertEqual(m.predict(row['context'])['value'], row['label'])

    def test_02_identifiable_partial_retained(self):
        for m in (self.ss, self.exact):
            r = m.predict({'a': '0'})
            self.assertEqual(r['value'], '0')
            self.assertEqual(r['completion_count'], 2)

    def test_03_ambiguous_partial_vetoed(self):
        for m in (self.ss, self.exact):
            self.assertEqual(m.predict({'a': '1'}, policy='baseline')['value'], '1')
            self.assertIsNone(m.predict({'a': '1'})['value'])

    def test_04_observed_only_overabstains(self):
        self.assertIsNone(self.ss.predict({'a': '0'}, policy='observed_only')['value'])

    def test_05_empty_stays_abstained(self):
        for policy in POLICIES:
            self.assertIsNone(self.ss.predict({}, policy=policy)['value'])

    def test_06_no_changed_label(self):
        for m in (self.ss, self.exact):
            for row in teachers():
                for deleted in (None, 'a', 'b'):
                    c = {k: v for k, v in row['context'].items() if k != deleted}
                    base = m.predict(c, policy='baseline')['value']
                    for policy in POLICIES:
                        self.assertIn(m.predict(c, policy=policy)['value'], (None, base))

    def test_07_consensus_ablation(self):
        self.assertEqual(self.ss.predict({'a': '0'}, policy='consensus_only')['value'], '0')
        self.assertIsNone(self.ss.predict({'a': '1'}, policy='consensus_only')['value'])

    def test_08_budget_exceeded_no_truncation_accept(self):
        limited = GuardedModel(self.ss.base, self.ss.evidence, self.ss.training, 1)
        self.assertEqual(limited.predict({'a': '0'})['reason'], 'completion_budget_exceeded')
        self.assertEqual(limited.predict({'a': '0', 'b': '1'})['value'], '0')

    def test_09_bad_budget(self):
        for value in (0, -1, True, 0.5, 4097):
            with self.assertRaises(ValueError):
                GuardedModel(self.ss.base, self.ss.evidence, self.ss.training, value)

    def test_10_unknown_value(self):
        with self.assertRaisesRegex(ValueError, 'unknown_field_value'):
            self.ss.predict({'a': '?'})

    def test_11_unknown_field(self):
        with self.assertRaisesRegex(ValueError, 'unknown_context_fields'):
            self.ss.predict({'oracle': '0'})

    def test_12_non_dictionary(self):
        with self.assertRaises(ValueError):
            self.ss.predict([])

    def test_13_invalid_policy(self):
        with self.assertRaises(ValueError):
            self.ss.predict({'a': '0'}, policy='oracle')

    def test_14_witness_zero_is_real_ablation(self):
        m = copy.deepcopy(self.ss)
        old = m.fingerprint
        for e in m.evidence:
            e.weights[:] = 0
        m.refresh()
        self.assertNotEqual(old, m.fingerprint)
        self.assertIsNone(m.predict({'a': '0'})['value'])
        self.assertEqual(m.predict({'a': '0'}, policy='consensus_only')['value'], '0')

    def test_15_base_zero_veto(self):
        m = copy.deepcopy(self.ss)
        for member in m.base.members:
            member['weights'][:] = 0
        m.base.refresh()
        m.refresh()
        self.assertIsNone(m.predict({'a': '0'})['value'])

    def test_16_unsupported_candidate_family(self):
        m = copy.deepcopy(self.ss)
        m.base.training['supported'] = False
        m.base.refresh()
        m.refresh()
        self.assertEqual(m.predict({'a': '0'})['reason'], 'unsupported_or_overflow')

    def test_17_product_cannot_gain_answers(self):
        m = model(representation='product')
        self.assertIsNone(m.predict({'a': '0'})['value'])

    def test_18_train_oracle_extra_field_rejected(self):
        rows = teachers()
        rows[0]['oracle'] = '1'
        with self.assertRaisesRegex(ValueError, 'unexpected_teacher_fields'):
            train_model(rows, teachers(), teachers())

    def test_19_witness_only_matching_teachers(self):
        rows = teachers()
        rows[0]['label'] = '1'
        with self.assertRaisesRegex(ValueError, 'witness_teacher_must_match_base_training'):
            attach(self.ss.base, rows)

    def test_20_no_exact_table_in_ss(self):
        self.assertTrue(all(not e.entries for e in self.ss.evidence))
        self.assertTrue(all(not member['counts'] for member in self.ss.base.members))

    def test_21_no_false_inference_permission(self):
        self.assertIs(self.ss.predict({'a': '0'})['eligible_for_inference'], False)
        self.assertIs(self.ss.meta['eligible_for_inference'], False)

    def test_22_save_reload(self):
        for m in (self.ss, self.exact):
            with tempfile.TemporaryDirectory(prefix='l12test-') as d:
                path = Path(d) / 'model'
                m.save(path)
                loaded = GuardedModel.load(path)
                self.assertEqual(loaded.fingerprint, m.fingerprint)
                for context in ({'a': '0'}, {'a': '1'}, {}):
                    self.assertEqual(m.predict(context), loaded.predict(context))

    def test_23_refit_determinism(self):
        self.assertEqual(model().fingerprint, self.ss.fingerprint)

    def test_24_tampered_metadata(self):
        with tempfile.TemporaryDirectory(prefix='l12test-') as d:
            p = Path(d) / 'model'
            self.ss.save(p)
            obj = json.loads((p / 'guard.json').read_text(encoding='utf-8'))
            obj['metadata']['max_completions'] = 1
            (p / 'guard.json').write_text(json.dumps(obj), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'guard_fingerprint_mismatch'):
                GuardedModel.load(p)

    def test_25_tampered_weights(self):
        with tempfile.TemporaryDirectory(prefix='l12test-') as d:
            p = Path(d) / 'model'
            self.ss.save(p)
            np.savez(p / 'witnesses.npz', member_0=self.ss.evidence[0].weights + .01)
            with self.assertRaisesRegex(ValueError, 'guard_fingerprint_mismatch'):
                GuardedModel.load(p)

    def test_26_model_extra_file(self):
        with tempfile.TemporaryDirectory(prefix='l12test-') as d:
            p = Path(d) / 'model'
            self.ss.save(p)
            (p / 'oracle.json').write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'invalid_guard_inventory'):
                GuardedModel.load(p)

    def test_27_changed_base_detected(self):
        with tempfile.TemporaryDirectory(prefix='l12test-') as d:
            p = Path(d) / 'model'
            self.ss.save(p)
            base = Model.load(p / 'base')
            base.threshold += .01
            base.refresh()
            obj = {'metadata': base.meta, 'fingerprint': base.fingerprint}
            (p / 'base/model.json').write_text(json.dumps(obj), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'guard_base_mismatch'):
                GuardedModel.load(p)

    def test_28_nonfinite_weights(self):
        with tempfile.TemporaryDirectory(prefix='l12test-') as d:
            p = Path(d) / 'model'
            self.ss.save(p)
            w = self.ss.evidence[0].weights.copy()
            w[0, 0] = np.nan
            np.savez(p / 'witnesses.npz', member_0=w)
            with self.assertRaisesRegex(ValueError, 'invalid_witness_weights'):
                GuardedModel.load(p)


class WitnessTests(unittest.TestCase):
    def test_29_dedup_not_frequency(self):
        rows = teachers()
        for backend in ('ss', 'exact'):
            a = build_evidence(rows, ['a', 'b'], ['0', '1'], 512, 'unit', backend)
            b = build_evidence(rows * 4, ['a', 'b'], ['0', '1'], 512, 'unit', backend)
            np.testing.assert_array_equal(a.weights, b.weights)
            self.assertEqual(a.entries, b.entries)

    def test_30_conflicting_teacher_is_not_unique(self):
        rows = teachers() + [{'context': {'a': '0', 'b': '0'}, 'label': '1'}]
        for backend in ('ss', 'exact'):
            e = build_evidence(rows, ['a', 'b'], ['0', '1'], 2048, 'unit', backend)
            r = e.assess({'a': '0', 'b': '0'}, '0')
            self.assertEqual(r['hits'], ['0', '1'])
            self.assertFalse(r['supported'])

    def test_31_missing_full_key(self):
        e = build_evidence(teachers()[:3], ['a', 'b'], ['0', '1'], 2048, 'unit', 'exact')
        self.assertEqual(e.assess({'a': '1', 'b': '1'}, '1')['hits'], [])

    def test_32_cannot_query_partial_witness(self):
        e = build_evidence(teachers(), ['a', 'b'], ['0', '1'], 512, 'unit', 'ss')
        with self.assertRaisesRegex(ValueError, 'witness_requires_complete_selected_key'):
            e.scores({'a': '0'})

    def test_33_label_permutation_learned(self):
        rows = teachers()
        for row in rows:
            row['label'] = 'green' if row['label'] == '0' else 'red'
        m = train_model(rows, rows, rows, dimension=512, seed='unit')[0]
        self.assertEqual(m.predict({'a': '0'})['value'], 'green')

    def test_34_nuisance_projection_not_full_input_table(self):
        rows = [dict(context=dict(r['context'], style=str(i)), label=r['label']) for r in teachers() for i in range(2)]
        m = train_model(rows, rows, rows, dimension=512, seed='unit')[0]
        self.assertEqual(m.base.members[0]['mask'], ['a', 'b'])
        self.assertEqual(m.predict({'a': '0'})['value'], '0')

    def test_35_all_candidates_required(self):
        m = copy.deepcopy(SufficiencyTests.ss)
        m.base.members.append(copy.deepcopy(m.base.members[0]))
        m.base.books.append(copy.deepcopy(m.base.books[0]))
        m.evidence.append(copy.deepcopy(m.evidence[0]))
        m.evidence[1].weights[:] = 0
        m.base.refresh()
        m.refresh()
        self.assertIsNone(m.predict({'a': '0'})['value'])
        self.assertEqual(m.predict({'a': '0'})['completion_count'], 4)

    def test_36_functional_ulp_not_strict_identity(self):
        from plm_l1_v012.portability import compare
        m = copy.deepcopy(SufficiencyTests.ss)
        w = m.evidence[0].weights
        w.real[:] = np.nextafter(w.real, np.inf)
        m.refresh()
        r = compare(SufficiencyTests.ss, m, [{'a': '0'}, {'a': '1'}, {}])
        self.assertTrue(r['functional_passed'])
        self.assertFalse(r['strict_fingerprint_equal'])

    def test_37_large_coefficient_difference_not_functional(self):
        from plm_l1_v012.portability import compare
        m = copy.deepcopy(SufficiencyTests.ss)
        m.evidence[0].weights += .01
        m.refresh()
        self.assertFalse(compare(SufficiencyTests.ss, m, [{'a': '0'}])['functional_passed'])

    def test_38_paired_worlds_have_identical_learning_information(self):
        from evaluation.cases import paired_worlds
        simple, hidden = paired_worlds('unit')
        for name in ('train', 'selection', 'calibration'):
            self.assertEqual(simple[name], hidden[name])
        self.assertNotEqual(simple['completion_oracle'], hidden['completion_oracle'])
        a = train_model(simple['train'], simple['selection'], simple['calibration'], backend='exact')[0]
        b = train_model(hidden['train'], hidden['selection'], hidden['calibration'], backend='exact')[0]
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_39_protocol_agrees_with_runtime(self):
        from plm_l1_v012.core import MAX_COMPLETIONS
        from plm_l1_v012.evidence import SUPPORT_THRESHOLD
        from evaluation.integrity import ROOT
        p = json.loads((ROOT / 'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
        self.assertEqual(p['max_completions'], MAX_COMPLETIONS)
        self.assertEqual(p['support_threshold'], SUPPORT_THRESHOLD)
        self.assertEqual(p['policies'], list(POLICIES))

    def test_40_new_query_sets_unique_and_disjoint(self):
        from evaluation.cases import new_tasks, query_stages
        from evaluate import disjoint
        for task in new_tasks('unit'):
            self.assertTrue(disjoint(task))
            for kind, queries in query_stages(task, True):
                if kind.startswith('semantic'):
                    self.assertEqual(len(queries), len({canonical(q['context']) for q in queries}))


if __name__ == '__main__':
    unittest.main()
