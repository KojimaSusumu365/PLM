import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_multicode.model import Model, SPECS, policy, decide
from ss_multicode.learning import Learner, teacher
from evaluation.cases import make_case, stream, validate
from evaluation.metrics import metrics, grid, calibration_rows, fixed_policies

C = {'f0': '0', 'f1': '1', 'f2': '2', 'f3': '3'}
C2 = dict(C, f0='4')


def teach(s, context=C, label='0'):
    q = s.question(context)['request']; return s.answer(q, teacher(q, label))


class ModelTests(unittest.TestCase):
    def test_01_equal_coefficient_budget(self):
        for a in ('single512', 'concat512', 'multi4', 'clone4', 'checked'):
            self.assertEqual(Model(a).storage()['coefficient_bytes'], 32768)
        self.assertEqual(Model('single128').storage()['coefficient_bytes'], 8192)

    def test_02_independent_banks(self):
        b, _ = Model('multi4').vectors([C])
        for i in range(1, 4): self.assertFalse(np.array_equal(b[0, 0], b[0, i]))

    def test_03_clones_are_copies(self):
        b, _ = Model('clone4').vectors([C]); single, _ = Model('single128').vectors([C])
        for i in range(4): np.testing.assert_array_equal(b[0, i], single[0, 0])

    def test_04_unit_phase(self):
        b, z = Model('checked').vectors([C]); np.testing.assert_allclose(abs(b), 1); np.testing.assert_allclose(abs(z), 1)

    def test_05_checker_uses_distinct_codes(self):
        b, z = Model('checked').vectors([C]); self.assertFalse(np.array_equal(b[0, 0], z[0, 0, :128]))

    def test_06_joint_pair_changes_with_label(self):
        _, z = Model('checked').vectors([C]); self.assertFalse(np.array_equal(z[0, 0], z[0, 1]))

    def test_07_shared_residual_equals_flat_concat(self):
        s = Learner(Model('concat512')); flat = np.zeros((4, 512), complex)
        for c, label in [(C, '0'), (C2, '1'), (C, '2'), (C2, '1')] * 3:
            b, _ = s.model.vectors([c]); v = b[0].reshape(-1)
            target = np.array([int(str(y) == label) for y in range(4)])
            flat += .5 * (target - (flat.conj() @ v).real / 512)[:, None] * v[None, :]
            s = teach(s, c, label)
            np.testing.assert_allclose(s.model.readers.transpose(1, 0, 2).reshape(4, 512), flat, rtol=0, atol=2e-15)

    def test_08_local_and_shared_diverge_after_interference(self):
        a = Learner(Model('multi4')); b = Learner(Model('concat512'))
        for c, y in ((C, '0'), (C2, '1')):
            a = teach(a, c, y); b = teach(b, c, y)
        self.assertFalse(np.allclose(a.model.readers, b.model.readers))

    def test_09_clone_training_matches_single(self):
        a = Learner(Model('clone4')); b = Learner(Model('single128'))
        for c, y in [(C, '0'), (C2, '1'), (C, '3')] * 5:
            a = teach(a, c, y); b = teach(b, c, y)
        for i in range(4): np.testing.assert_array_equal(a.model.readers[i], b.model.readers[0])

    def test_10_pair_first_update_matches_formula(self):
        s = Learner(Model('checked')); _, z = s.model.vectors([C]); n = teach(s)
        np.testing.assert_array_equal(n.model.checker, .5 * z[0, 0])

    def test_11_pair_counterlabel_corrected(self):
        s = Learner(Model('checked'))
        for _ in range(12): s = teach(s, label='0')
        for _ in range(12): s = teach(s, label='1')
        scores = s.model.raw([C])['checker'][0]
        self.assertGreater(scores[1], .95); self.assertLess(abs(scores[0]), .05)

    def test_12_query_does_not_learn(self):
        s = Learner(Model('checked')); old = s.fingerprint; weights = s.model.readers.copy()
        for _ in range(4): s.question(C)
        self.assertEqual(s.fingerprint, old); np.testing.assert_array_equal(s.model.readers, weights)

    def test_13_previous_state_immutable(self):
        s = Learner(Model('multi4')); f = s.fingerprint; n = teach(s)
        self.assertEqual(s.fingerprint, f); self.assertTrue((s.model.readers == 0).all()); self.assertEqual(n.step, 1)

    def test_14_acceptance_does_not_change_learning(self):
        a = Learner(Model('multi4', acceptance=policy())); b = Learner(Model('multi4', acceptance=policy(reject_all=True)))
        for c, y in ((C, '0'), (C2, '1')): a = teach(a, c, y); b = teach(b, c, y)
        np.testing.assert_array_equal(a.model.readers, b.model.readers)

    def test_15_exact_unseen_rejected(self):
        s = teach(Learner(Model('exact'))); self.assertIsNone(s.model.predict([C2])[0]['accepted'])

    def test_16_exact_drift_overwrites(self):
        s = teach(teach(Learner(Model('exact'))), label='2'); self.assertEqual(s.model.predict([C])[0]['accepted'], '2')

    def test_17_invalid_contexts(self):
        for c in ({}, dict(C, f0='8'), dict(C, f0=0), dict(C, extra='0')):
            with self.assertRaises(ValueError): Model().predict([c])

    def test_18_no_ss_key_table(self):
        with self.assertRaises(ValueError): Model(entries={json.dumps(C): '0'})

    def test_19_invalid_weights(self):
        with self.assertRaises(ValueError): Model('multi4', readers=np.zeros((4, 4, 128), dtype=float))
        w = np.zeros((1, 4, 512), complex); w[0, 0, 0] = np.nan
        with self.assertRaises(ValueError): Model(readers=w)

    def test_20_global_phase_rotation_preserves_crosstalk(self):
        b, _ = Model('multi4').vectors([C, C2]); a, v = b[:, 0]; phase = np.exp(1j * .713)
        np.testing.assert_allclose(np.vdot(a, v), np.vdot(a * phase, v * phase), atol=1e-12)


class PolicyTests(unittest.TestCase):
    def raw(self, values, check=None):
        return {'readers': np.array([values], float), 'checker': np.array([check], float) if check is not None else np.empty((1, 0))}

    def test_21_no_support(self):
        self.assertEqual(decide(self.raw([[0, 0, 0, 0]]), policy())['accepted'][0], -1)

    def test_22_multiple_hits(self):
        self.assertEqual(decide(self.raw([[.8, .6, 0, 0]]), policy())['accepted'][0], -1)

    def test_23_tie_tentative(self):
        self.assertEqual(decide(self.raw([[.6, .6, 0, 0]]), policy())['tentative'][0], -1)

    def test_24_bank_disagreement(self):
        raw = self.raw([[.9, 0, 0, 0], [.9, 0, 0, 0], [.9, 0, 0, 0], [.1, .8, 0, 0]])
        self.assertEqual(decide(raw, policy(quorum=3))['accepted'][0], 0)
        self.assertEqual(decide(raw, policy(quorum=4))['accepted'][0], -1)

    def test_25_gate_does_not_repair_tentative(self):
        raw = self.raw([[.9, 0, 0, 0]], [.1, .9, 0, 0])
        ds = decide(raw, policy(check_threshold=.5))
        self.assertEqual(ds['tentative'][0], 0); self.assertEqual(ds['accepted'][0], -1)

    def test_26_check_passes_agreement(self):
        ds = decide(self.raw([[.9, 0, 0, 0]], [.8, .1, 0, 0]), policy(check_threshold=.5))
        self.assertEqual(ds['accepted'][0], 0)

    def test_27_check_no_support(self):
        self.assertEqual(decide(self.raw([[.9, 0, 0, 0]], [.1, .1, 0, 0]), policy(check_threshold=.5))['accepted'][0], -1)

    def test_28_check_multiple_hits(self):
        self.assertEqual(decide(self.raw([[.9, 0, 0, 0]], [.8, .6, 0, 0]), policy(check_threshold=.5))['accepted'][0], -1)

    def test_29_no_checker_available(self):
        with self.assertRaises(ValueError): decide(self.raw([[.9, 0, 0, 0]]), policy(check_threshold=.5))

    def test_30_invalid_policy(self):
        for p in (policy(threshold=-1), policy(quorum=2), policy(threshold=float('nan')), dict(policy(), truth=0)):
            with self.assertRaises(ValueError): decide(self.raw([[0, 0, 0, 0]]), p)

    def test_31_zero_results(self):
        for a in SPECS: self.assertEqual(Model(a).predict([]), [])

    def test_32_reject_all_full_reason(self):
        ds = decide(self.raw([[1, 0, 0, 0]]), policy(reject_all=True))
        self.assertEqual(ds['reason'][0], 'calibration_no_feasible_acceptance')

    def test_33_nonfinite_raw_rejected(self):
        with self.assertRaises(ValueError): decide(self.raw([[np.nan, 0, 0, 0]]), policy())

    def test_34_known_unknown_accounting(self):
        raw = {'readers': np.array([[[1, 0, 0, 0]], [[1, 0, 0, 0]], [[0, 0, 0, 0]]]), 'checker': np.empty((3, 0))}
        m = metrics(raw, policy(), [True, False, True], [0, -1, 1])
        self.assertEqual(m['accepted_correct'], 1); self.assertEqual(m['accepted_abstained'], 1); self.assertEqual(m['unseen_false_accept'], 1)

    def test_35_calibration_fallback(self):
        raw = {'readers': np.ones((2, 1, 4)) * 0, 'checker': np.empty((2, 0))}; raw['readers'][:, 0, 0] = 2
        rows, best = calibration_rows('single128', [{'raw': raw, 'known': [True, False], 'truth': [0, -1]}])
        self.assertTrue(best['policy']['reject_all']); self.assertEqual(best['metrics']['accepted_correct'], 0)

    def test_36_all_fixed_gates_are_subsets(self):
        rng = np.random.default_rng(33)
        raw = {'readers': rng.normal(.3, .4, (128, 3, 4)), 'checker': rng.normal(.3, .4, (128, 4))}
        base = decide(raw, policy())['accepted']
        for p in fixed_policies('checked').values():
            ds = decide(raw, p)['accepted']; self.assertTrue(np.all((ds < 0) | (ds == base)))


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.s = Learner(Model('checked')); self.req = self.s.question(C)['request']; self.fb = teacher(self.req, '0')

    def test_37_stale_request(self):
        new = self.s.answer(self.req, self.fb)
        with self.assertRaises(ValueError): new.answer(self.req, self.fb)

    def test_38_tampered_request(self):
        req = copy.deepcopy(self.req); req['context']['f0'] = '1'
        with self.assertRaises(ValueError): self.s.answer(req, self.fb)

    def test_39_pseudo_feedback(self):
        with self.assertRaises(ValueError): self.s.answer(self.req, dict(self.fb, source='model_prediction'))

    def test_40_extra_truth(self):
        with self.assertRaises(ValueError): self.s.answer(self.req, dict(self.fb, truth='0'))

    def test_41_unknown_label(self):
        with self.assertRaises(ValueError): self.s.answer(self.req, dict(self.fb, label='4'))

    def test_42_wrong_request_id(self):
        with self.assertRaises(ValueError): self.s.answer(self.req, dict(self.fb, request_id='wrong'))

    def test_43_prediction_envelope_rejected(self):
        with self.assertRaises(ValueError): self.s.answer(self.req, self.s.question(C))

    def test_44_truthful_source_not_authentication(self):
        new = self.s.answer(self.req, teacher(self.req, '3'))
        self.assertEqual(new.step, 1)  # accepts declared teacher without access to ground truth

    def test_45_data_disjointness_and_repeatability(self):
        case = make_case('unit-fixture'); self.assertTrue(validate(case)); self.assertEqual(case, make_case('unit-fixture'))

    def test_46_stream_counts(self):
        case = make_case('unit-fixture')
        for scenario in ('clean', 'noisy_first'):
            es = [e for b in stream(case, scenario) for e in b['events']]
            self.assertEqual(len(es), 896); self.assertEqual(len({e['id'] for e in es}), 192)
            self.assertEqual(sum(e['truth'] != e['teacher_label'] for e in es), 8 if scenario == 'noisy_first' else 0)

    def test_47_state_tamper_detected(self):
        with tempfile.TemporaryDirectory(prefix='mctest-') as temp:
            p = Path(temp) / 'learner'; self.s.save(p)
            file = p / 'learner.json'; o = json.loads(file.read_text()); o['state']['step'] = 9
            file.write_text(json.dumps(o), encoding='utf-8')
            with self.assertRaises(ValueError): Learner.load(p)

    def test_48_weight_tamper_detected(self):
        with tempfile.TemporaryDirectory(prefix='mctest-') as temp:
            p = Path(temp) / 'model'; self.s.model.save(p)
            np.savez(p / 'weights.npz', readers=self.s.model.readers + 1, checker=self.s.model.checker)
            with self.assertRaises(ValueError): Model.load(p)


def persistent_test(architecture):
    def test(self):
        s = Learner(Model(architecture))
        for _ in range(8): s = teach(s)
        with tempfile.TemporaryDirectory(prefix='mctest-') as temp:
            p = Path(temp) / 'learner'; s.save(p); new = Learner.load(p)
            self.assertEqual(s.fingerprint, new.fingerprint)
            self.assertEqual(s.model.predict([C, C2]), new.model.predict([C, C2]))
            self.assertFalse(new.model.predict([C])[0]['eligible_for_inference'])
            self.assertNotIn('buffer', new.state)
            with self.assertRaises(FileExistsError): new.save(p)
    return test


for arch in SPECS: setattr(BoundaryTests, 'test_persist_' + arch, persistent_test(arch))


if __name__ == '__main__': unittest.main()
