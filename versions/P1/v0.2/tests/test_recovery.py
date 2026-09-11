import unittest
from copy import deepcopy
from dataclasses import replace
import numpy as np
import plm_p1_v02
from plm_p1.core import PhaseCodebook, encode, channel, symbol, canonical, decode
from plm_p1_v02.recovery import Receiver, AdaptivePolicy, validate_catalogue
from plm_p1_v02.fixtures import make_frames, entity_candidates, public_catalogue, DOC
from plm_p1_v02.partition import encode_partitioned, template


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = PhaseCodebook(2048, "unit-tests-v02")
        cls.frames = make_frames(4)
        cls.y = encode(cls.frames, cls.book)
        cls.masked, cls.mask = channel(cls.y, seed=555, keep_fraction=.25, noise_std=.15, jitter_std=.1)
        cls.catalogue = public_catalogue()
        cls.candidates = entity_candidates()
        cls.receiver = Receiver(cls.masked, cls.mask, cls.book, cls.catalogue)

    def query(self, receiver=None, event="event-000", role="subject", candidates=None, **kwargs):
        return (receiver or self.receiver).scores(DOC, event, role, self.candidates if candidates is None else candidates, **kwargs)

    def test_nominal_all_entity_slots(self):
        r = Receiver(self.y, None, self.book, self.catalogue)
        for f in self.frames:
            for role in ("subject", "object"):
                self.assertEqual(self.query(r, f["event_id"], role)["selected"], f["slots"][role])

    def test_masked_all_entity_slots(self):
        for f in self.frames:
            for role in ("subject", "object"):
                self.assertEqual(self.query(event=f["event_id"], role=role)["selected"], f["slots"][role])

    def test_absent_address_is_not_membership_rejected(self):
        a = self.query(event="absent-event-000")
        b = self.query(event="not-even-in-catalogue")
        self.assertIsNone(a["selected"])
        self.assertIsNone(b["selected"])
        self.assertTrue(a["top_candidates"] and b["top_candidates"])

    def test_true_absent_dictionary(self):
        self.assertIsNone(self.query(candidates=self.candidates[1:])["selected"])

    def test_single_candidate_null(self):
        self.assertIsNone(self.query(event="absent-event-000", candidates=self.candidates[:1])["selected"])

    def test_zero_signal_abstains(self):
        r = Receiver(np.zeros(2048, complex), None, self.book, self.catalogue)
        self.assertIsNone(self.query(r)["selected"])

    def test_zero_observation_abstains(self):
        r = Receiver(self.y, np.zeros(2048, bool), self.book, self.catalogue)
        self.assertEqual(self.query(r)["reason"], "insufficient_observed_components")

    def test_insufficient_residual_dof_abstains(self):
        mask = np.arange(2048) < 160
        r = Receiver(self.y, mask, self.book, self.catalogue)
        self.assertEqual(self.query(r)["reason"], "insufficient_residual_degrees_of_freedom")

    def test_overcomplete_catalogue_abstains(self):
        r = Receiver(self.y, np.arange(2048)<128, self.book, public_catalogue(12))
        self.assertEqual(self.query(r)["reason"], "insufficient_residual_degrees_of_freedom")

    def test_empty_candidates(self):
        self.assertEqual(self.query(candidates=[])["reason"], "empty_candidate_dictionary")

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError): self.query(candidates=[self.candidates[0]]*2)

    def test_dictionary_order_invariance(self):
        self.assertEqual(self.query(), self.query(candidates=list(reversed(self.candidates))))

    def test_mask_hides_unobserved_values(self):
        changed = self.masked.copy()
        changed[~self.mask] = 1e10 + 3j
        self.assertEqual(self.query(), self.query(Receiver(changed, self.mask, self.book, self.catalogue)))

    def test_catalogue_is_defensively_copied(self):
        c = deepcopy(self.catalogue)
        r = Receiver(self.masked, self.mask, self.book, c)
        c["addresses"].clear()
        self.assertEqual(self.query(), self.query(r))

    def test_signal_is_defensively_copied(self):
        y = self.masked.copy()
        r = Receiver(y, self.mask, self.book, self.catalogue)
        y[:] = 0
        self.assertEqual(self.query(), self.query(r))

    def test_nuisance_cancelled_without_assignments(self):
        nuisance = deepcopy(self.frames)
        for f in nuisance:
            f["slots"] = {k:v for k,v in f["slots"].items() if k not in {"subject", "object"}}
        r = Receiver(encode(nuisance, self.book), self.mask, self.book, self.catalogue)
        q, residual, rank = r.context(DOC, "event-000", "subject")
        self.assertLess(np.linalg.norm(residual), 1e-9)
        self.assertEqual(rank, 88)

    def test_projection_orthogonality(self):
        q, residual, rank = self.receiver.context(DOC, "event-000", "subject")
        self.assertLess(np.linalg.norm(q.conj().T @ residual), 1e-9)

    def test_state_query_excludes_own_role(self):
        for role in ("predicate", "polarity", "modality", "semantic_status", "applied"):
            r = self.query(role=role, candidates=self.catalogue["vocabulary"][role])
            self.assertEqual(r["selected"], self.frames[0]["slots"][role])
            self.assertLess(r["nuisance_rank"], 88)

    def test_partition_energy_each_binding(self):
        f = self.frames[0]
        for role, value in f["slots"].items():
            t = template(self.book, DOC, f["event_id"], role, value)
            self.assertAlmostEqual(float(np.vdot(t,t).real),2048,places=8)

    def test_partition_preserves_state_roles(self):
        a = encode_partitioned(self.frames,self.book)
        changed = deepcopy(self.frames)
        changed[0]["slots"]["polarity"] = symbol("state","polarity:positive")
        b = encode_partitioned(changed,self.book)
        self.assertTrue(np.array_equal(a[:1024],b[:1024]))
        self.assertFalse(np.allclose(a[1024:],b[1024:]))

    def test_symbol_identity_and_roles_remain_distinct(self):
        a,b = self.query(role="subject"),self.query(role="object")
        self.assertNotEqual(a["selected"],b["selected"])
        self.assertEqual(a["selected"]["scope"],DOC)

    def test_unknown_query_role(self):
        with self.assertRaises(ValueError): self.query(role="gold")

    def test_no_inference_promotion(self):
        self.assertIs(self.query()["eligible_for_inference"],False)
        self.assertIn("not_probability", self.query()["score_kind"])

    def test_threshold_depends_on_candidate_count(self):
        p = AdaptivePolicy(min_amplitude=.00001,min_margin=.00001)
        one = self.query(candidates=self.candidates[:1],policy=p)
        many = self.query(policy=p)
        self.assertGreater(many["amplitude_threshold"],one["amplitude_threshold"])

    def test_no_projection_ablation_has_zero_rank(self):
        r = Receiver(self.masked,self.mask,self.book,self.catalogue,project=False)
        self.assertEqual(self.query(r)["nuisance_rank"],0)

    def test_quarter_turn_needs_sync(self):
        r = Receiver(self.y*1j,None,self.book,self.catalogue)
        self.assertIsNone(self.query(r)["selected"])

    def test_empty_catalogue_is_valid(self):
        c = deepcopy(self.catalogue)
        c["addresses"] = []
        r = Receiver(self.y,None,self.book,c)
        self.assertEqual(self.query(r)["nuisance_rank"],0)


def invalid_policy_test(field,value):
    def test(self):
        with self.assertRaises(ValueError): replace(AdaptivePolicy(), **{field:value}).validate()
    return test


for i,(field,value) in enumerate([( "min_components",True),("min_components",0),("min_residual_dof",0),("min_retained_fraction",1.01),("min_retained_fraction",0),("min_amplitude",float("nan")),("family_alpha",0),("family_alpha",1),("min_margin",-1),("gap_z",float("inf"))]):
    setattr(RecoveryTests,f"test_invalid_policy_{i:02d}",invalid_policy_test(field,value))


def invalid_catalogue_test(mutate):
    def test(self):
        c=deepcopy(self.catalogue)
        mutate(c)
        with self.assertRaises((ValueError,TypeError)): validate_catalogue(c)
    return test


for i,mutate in enumerate([
    lambda c:c.update(gold={}), lambda c:c.update(format="unknown"),
    lambda c:c["addresses"].append(c["addresses"][0]),
    lambda c:c["addresses"][0].update(present=True),
    lambda c:c["vocabulary"].update(subject=[symbol("entity","x",DOC)]),
    lambda c:c["vocabulary"].update(polarity=[]),
    lambda c:c["vocabulary"]["polarity"].append(c["vocabulary"]["polarity"][0]),
    lambda c:c["vocabulary"].update(polarity=[symbol("predicate","wrong")]),
    lambda c:c["vocabulary"].update(predicate=[symbol("predicate","x",DOC)])]):
    setattr(RecoveryTests,f"test_invalid_catalogue_{i:02d}",invalid_catalogue_test(mutate))


if __name__ == "__main__": unittest.main()
