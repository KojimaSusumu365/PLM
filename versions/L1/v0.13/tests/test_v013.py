import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from plm_l1_v013.algebra import canonical, digest
from plm_l1_v013.core import Model
from plm_l1_v013.training import fit
from plm_l1_v013.teaching import Session


def example_rows():
    return [{'context': dict(zip('abc', map(str, (a, b, c)))), 'label': str(a)}
            for a, b, c in itertools.product((0, 1), repeat=3) if (a, b, c) != (1, 1, 1)]


def settings(backend='ss', retention='all'):
    return dict(backend=backend, dimension=512, seed='unit', retention=retention)


def session(backend='ss'):
    return Session(example_rows(), [{'id': 'missing', 'context': dict(a='1', b='1', c='1')}], settings(backend))


class MemoryTests(unittest.TestCase):
    def test_01_keep_larger_consistent_dependency(self):
        m = fit(example_rows(), **settings())[0]
        self.assertIn(['a'], [x['mask'] for x in m.members])
        self.assertIn(['a', 'b', 'c'], [x['mask'] for x in m.members])

    def test_02_unseen_cell_is_not_false(self):
        for backend in ('ss', 'exact'):
            m = fit(example_rows(), **settings(backend))[0]
            p = m.predict(dict(a='1', b='1', c='1'))
            self.assertIsNone(p['value'])
            self.assertEqual(p['possible_labels'], ['0', '1'])
            self.assertTrue(p['learning_insufficient'])
            self.assertFalse(p['input_insufficient'])

    def test_03_minimal_ablation_confirms(self):
        m = fit(example_rows(), **settings(retention='minimal'))[0]
        self.assertEqual(m.predict(dict(a='1', b='1', c='1'))['value'], '1')

    def test_04_known_query_retained(self):
        m = fit(example_rows(), **settings())[0]
        self.assertEqual(m.predict(dict(a='0', b='1', c='1'))['value'], '0')

    def test_05_missing_input_after_complete_learning(self):
        rows = example_rows() + [{'context': dict(a='1', b='1', c='1'), 'label': '1'}]
        m = fit(rows, **settings())[0]
        p = m.predict(dict(b='1', c='1'))
        self.assertEqual(p['reason'], 'input_insufficient')
        self.assertFalse(p['learning_insufficient'])

    def test_06_missing_and_learning_flags(self):
        m = fit(example_rows(), **settings())[0]
        p = m.predict({})
        self.assertTrue(p['input_insufficient'])
        self.assertTrue(p['learning_insufficient'])

    def test_07_counterexample_changes_dependency(self):
        s = session()
        updated = s.answer(s.choose(), '0')
        self.assertNotIn(['a'], [m['mask'] for m in updated.model.members])
        self.assertEqual(updated.model.predict(dict(a='1', b='1', c='1'))['value'], '0')
        self.assertEqual(len(s.rows), 7)

    def test_08_confirmation_resolves_unknown(self):
        s = session()
        updated = s.answer(s.choose(), '1')
        self.assertEqual(updated.model.predict(dict(a='1', b='1', c='1'))['value'], '1')

    def test_09_exact_consistent_masks_only_shrink(self):
        s = session('exact')
        before = {tuple(m['mask']) for m in s.model.members}
        after = s.answer(s.choose(), '0')
        self.assertTrue({tuple(m['mask']) for m in after.model.members} <= before)

    def test_10_zero_memory_never_confirms(self):
        m = fit(example_rows(), **settings())[0]
        old = m.fingerprint
        for member in m.members:
            member['weights'][:] = 0
        m.refresh()
        self.assertNotEqual(old, m.fingerprint)
        self.assertTrue(all(p['value'] is None for p in m.predict_many([r['context'] for r in example_rows()])))

    def test_11_no_runtime_key_table_ss(self):
        m = fit(example_rows(), **settings())[0]
        self.assertTrue(all(not x['entries'] for x in m.members))
        self.assertNotIn('rows', m.meta)

    def test_12_disallowed_order(self):
        for order in (0, 4, True):
            with self.assertRaises(ValueError):
                fit(example_rows(), max_order=order)

    def test_13_unknown_value_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown_field_value'):
            session().model.predict({'a': '?'})

    def test_14_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            session().model.predict({'oracle': '1'})

    def test_15_teacher_oracle_extra_rejected(self):
        rows = example_rows()
        rows[0]['oracle'] = '0'
        with self.assertRaisesRegex(ValueError, 'unexpected_teacher_fields'):
            fit(rows)

    def test_16_contradiction_exhausts_family(self):
        rows = example_rows() + [{'context': dict(a='0', b='0', c='0'), 'label': '1'}]
        m = fit(rows)[0]
        self.assertEqual(m.members, [])
        self.assertEqual(m.predict({})['reason'], 'hypothesis_family_exhausted')
        self.assertEqual(m.select(session().pool)['status'], 'no_request')

    def test_17_outside_order4_is_not_claimed(self):
        rows = [{'context': dict(zip('abcd', map(str, bits))), 'label': str(sum(bits) % 2)} for bits in itertools.product((0, 1), repeat=4)]
        self.assertEqual(fit(rows)[0].members, [])

    def test_18_exact_version_space_independent_enumeration(self):
        contexts = [dict(zip('ab', map(str, bits))) for bits in itertools.product((0, 1), repeat=2)]
        rows = [{'context': contexts[0], 'label': '0'}, {'context': contexts[3], 'label': '1'}]
        functions = [ys for ys in itertools.product('01', repeat=4) if ys[0] == '0' and ys[3] == '1']
        m = fit(rows, backend='exact')[0]
        for q in contexts + [{'a': '0'}, {'b': '1'}, {}]:
            possible = sorted({ys[i] for ys in functions for i, c in enumerate(contexts) if all(c[k] == v for k, v in q.items())})
            self.assertEqual(m.predict(q)['possible_labels'], possible)

    def test_19_field_roles_remain_distinct(self):
        rows = [{'context': dict(a=a, b=b), 'label': a + '|' + b} for a, b in itertools.product('01', repeat=2)]
        m = fit(rows)[0]
        self.assertEqual(m.predict(dict(a='0', b='1'))['value'], '0|1')
        self.assertEqual(m.predict(dict(a='1', b='0'))['value'], '1|0')

    def test_20_batch_equal_to_single(self):
        m = fit(example_rows())[0]
        contexts = [r['context'] for r in example_rows()] + [{}, {'a': '0'}]
        self.assertEqual(m.predict_many(contexts), [m.predict(c) for c in contexts])

    def test_21_no_inference_opening(self):
        self.assertIs(session().model.predict({})['eligible_for_inference'], False)

    def test_22_repeated_teachers_deduplicated(self):
        a = fit(example_rows())[0]
        b = fit(example_rows() * 2)[0]
        for x, y in zip(a.members, b.members):
            np.testing.assert_array_equal(x['weights'], y['weights'])
        self.assertNotEqual(a.fingerprint, b.fingerprint)


class TeachingTests(unittest.TestCase):
    def test_23_unseen_combinations_get_query_priority(self):
        m = session().model
        pool = session().pool + [{'id': 'known', 'context': dict(a='0', b='0', c='0')}]
        self.assertEqual(m.select(pool)['id'], 'missing')

    def test_24_pool_label_forbidden(self):
        pool = session().pool
        pool[0]['label'] = '0'
        with self.assertRaisesRegex(ValueError, 'pool_must_be_unlabeled'):
            session().model.select(pool)

    def test_25_pool_truth_extra_forbidden(self):
        pool = session().pool
        pool[0]['oracle'] = {'0': 1}
        with self.assertRaises(ValueError):
            session().model.select(pool)

    def test_26_pool_ids_unique(self):
        with self.assertRaises(ValueError):
            session().model.select(session().pool * 2)

    def test_27_pool_complete_input_required(self):
        with self.assertRaises(ValueError):
            session().model.select([{'id': 'p', 'context': {'a': '1'}}])

    def test_28_pool_training_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pool_overlaps_observed_teachers'):
            Session(example_rows(), [{'id': 'p', 'context': example_rows()[0]['context']}], settings())

    def test_29_random_ignores_memory_scores(self):
        m = session().model
        pool = session().pool + [{'id': 'known', 'context': dict(a='0', b='0', c='0')}]
        before = [r['id'] for r in m.rank_pool(pool, 'random', 'r')]
        for member in m.members:
            member['weights'][:] = 0
        self.assertEqual(before, [r['id'] for r in m.rank_pool(pool, 'random', 'r')])

    def test_30_request_is_label_free(self):
        r = session().choose()
        self.assertNotIn('label', r)
        self.assertIs(r['diagnostics']['score_is_probability'], False)

    def test_31_stale_request_rejected(self):
        s = session()
        request = s.choose()
        updated = s.answer(request, '0')
        with self.assertRaisesRegex(ValueError, 'stale_teacher_request'):
            updated.answer(request, '0')

    def test_32_tampered_request_rejected(self):
        s = session()
        request = s.choose()
        request['diagnostics']['score'] += .01
        with self.assertRaisesRegex(ValueError, 'request_does_not_match_selection'):
            s.answer(request, '0')

    def test_33_unknown_label_requires_review(self):
        s = session()
        with self.assertRaisesRegex(ValueError, 'new_label_requires_scope_review'):
            s.answer(s.choose(), 'not-in-inventory')

    def test_34_one_response_one_teacher(self):
        s = session()
        t = s.answer(s.choose(), '0')
        self.assertEqual(len(t.rows), len(s.rows) + 1)
        self.assertEqual(len(t.pool), 0)
        self.assertEqual(len(t.receipts), 1)

    def test_35_empty_pool_stops(self):
        self.assertEqual(session().model.select([])['reason'], 'pool_exhausted')

    def test_36_teacher_label_changes_next_model(self):
        s = session()
        self.assertNotEqual(s.answer(s.choose(), '0').model.fingerprint, s.answer(s.choose(), '1').model.fingerprint)

    def test_37_failed_answer_no_mutation(self):
        s = session()
        before = canonical([s.rows, s.pool, s.receipts, s.model.fingerprint])
        with self.assertRaises(ValueError):
            s.answer(s.choose(), 'unknown')
        self.assertEqual(before, canonical([s.rows, s.pool, s.receipts, s.model.fingerprint]))


class PersistenceTests(unittest.TestCase):
    def test_38_save_load_model(self):
        for backend in ('ss', 'exact'):
            s = session(backend)
            with tempfile.TemporaryDirectory(prefix='l13test-') as d:
                p = Path(d) / 'model'
                s.model.save(p)
                loaded = Model.load(p)
                self.assertEqual(loaded.fingerprint, s.model.fingerprint)
                self.assertEqual(loaded.select(s.pool), s.choose())

    def test_39_session_resume(self):
        s = session()
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            p = Path(d) / 'session'
            s.save(p)
            loaded = Session.load(p)
            self.assertEqual(loaded.choose(), s.choose())
            self.assertEqual(loaded.answer(loaded.choose(), '0').model.fingerprint, s.answer(s.choose(), '0').model.fingerprint)

    def test_40_model_tamper_rejected(self):
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            p = Path(d) / 'model'
            m = session().model
            m.save(p)
            arrays = {f'm{i}': x['weights'].copy() for i, x in enumerate(m.members)}
            arrays['m0'] += .01
            np.savez(p / 'weights.npz', **arrays)
            with self.assertRaisesRegex(ValueError, 'model_fingerprint_mismatch'):
                Model.load(p)

    def test_41_nonfinite_weight_rejected(self):
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            p = Path(d) / 'model'
            m = session().model
            m.save(p)
            arrays = {f'm{i}': x['weights'].copy() for i, x in enumerate(m.members)}
            arrays['m0'][0, 0] = np.nan
            np.savez(p / 'weights.npz', **arrays)
            with self.assertRaisesRegex(ValueError, 'invalid_weights'):
                Model.load(p)

    def test_42_extra_runtime_truth_file_rejected(self):
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            p = Path(d) / 'model'
            session().model.save(p)
            (p / 'oracle.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                Model.load(p)

    def test_43_session_tamper_rejected(self):
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            p = Path(d) / 'session'
            session().save(p)
            obj = json.loads((p / 'session.json').read_text(encoding='utf-8'))
            obj['state']['rows'][0]['label'] = '1'
            (p / 'session.json').write_text(json.dumps(obj), encoding='utf-8')
            with self.assertRaises(ValueError):
                Session.load(p)

    def test_44_fresh_directory_required(self):
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            with self.assertRaises(FileExistsError):
                session().model.save(d)

    def test_45_refit_determinism(self):
        self.assertEqual(session().model.fingerprint, session().model.fingerprint)

    def test_46_whole_family_empty_persists(self):
        rows = example_rows() + [{'context': dict(a='0', b='0', c='0'), 'label': '1'}]
        m = fit(rows)[0]
        with tempfile.TemporaryDirectory(prefix='l13test-') as d:
            p = Path(d) / 'model'
            m.save(p)
            self.assertEqual(Model.load(p).predict({})['reason'], 'hypothesis_family_exhausted')


class EvaluationTests(unittest.TestCase):
    def test_47_disjoint_teacher_pool_test(self):
        from evaluation.cases import tasks, disjoint
        for t in tasks('unit'):
            self.assertTrue(disjoint(t))

    def test_48_paired_worlds_label_blind_initial_choice(self):
        from evaluation.cases import paired
        a, b = paired('unit')
        self.assertEqual(a['initial'], b['initial'])
        self.assertEqual(a['pool'], b['pool'])
        self.assertNotEqual(a['teacher_answers'], b['teacher_answers'])
        sa = Session(a['initial'], a['pool'], settings())
        sb = Session(b['initial'], b['pool'], settings())
        self.assertEqual(sa.choose(), sb.choose())

    def test_49_partial_hidden_correct_is_not_justified(self):
        from evaluation.metrics import measure
        self.assertEqual(measure(['0'], [['0', '1']])['wrong'], 1)

    def test_50_protocol_matches_runtime(self):
        from evaluation.cases import ROOT
        from plm_l1_v013.core import MAX_ORDER, MAX_FIELDS, MAX_CANDIDATES, SUPPORT_THRESHOLD
        p = json.loads((ROOT / 'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
        self.assertEqual((p['max_order'], p['max_fields'], p['candidate_cap'], p['support_threshold']), (MAX_ORDER, MAX_FIELDS, MAX_CANDIDATES, SUPPORT_THRESHOLD))

    def test_51_functional_ulp_is_not_strict_identity(self):
        from plm_l1_v013.portability import compare
        a = session().model
        b = copy.deepcopy(a)
        for m in b.members:
            m['weights'].real[:] = np.nextafter(m['weights'].real, np.inf)
        b.refresh()
        check = compare(a, b, [r['context'] for r in example_rows()], session().pool)
        self.assertTrue(check['functional_passed'])
        self.assertFalse(check['strict_fingerprint_equal'])

    def test_52_functional_large_change_rejected(self):
        from plm_l1_v013.portability import compare
        a = session().model
        b = copy.deepcopy(a)
        b.members[0]['weights'] += .01
        b.refresh()
        self.assertFalse(compare(a, b, [r['context'] for r in example_rows()], session().pool)['functional_passed'])

    def test_53_query_does_not_mutate_fingerprint(self):
        m = session().model
        old = m.fingerprint
        m.predict({})
        m.select(session().pool)
        m.refresh()
        self.assertEqual(old, m.fingerprint)

    def test_54_no_labeled_pool_even_when_family_exhausted(self):
        rows = example_rows() + [{'context': dict(a='0', b='0', c='0'), 'label': '1'}]
        m = fit(rows)[0]
        with self.assertRaisesRegex(ValueError, 'pool_must_be_unlabeled'):
            m.select([{'id': 'p', 'context': dict(a='1', b='1', c='1'), 'label': '1'}])


if __name__ == '__main__':
    unittest.main()
