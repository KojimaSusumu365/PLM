import copy
import inspect
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v05.training import fit
from plm_l1_v05.runtime import Model
from plm_l1_v05.algebra import Book
from plm_l1_v05.projection import Space,fit_memory
from evaluation_support import data,train_for,FOLDS,paired_models,interpret
from measurements import noisy_packet,memory_load,vector_digest


class ConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model,cls.old=paired_models(train_for(FOLDS[0]),"checked-development-0",8192)
        cls.low,cls.old_low=paired_models(train_for(FOLDS[0]),"parts-stress-0",128)
        cls.text="花子を太郎が助けなかった。"
        cls.meaning=interpret(cls.text)
        cls.packet=cls.model.encode(cls.meaning)

    def test_known_failures_abstain_without_packet(self):
        for text in ("花子が健太を褒めた。","健太を花子が褒めた。"):
            r=self.low.read(text)
            self.assertEqual(r["status"],"abstain")
            self.assertEqual(r["reason"],"meaning_signal_unrecoverable")
            self.assertIsNone(r["packet"])

    def test_legacy_failure_reproduced(self):
        r=self.old_low.read("花子が健太を褒めた。")
        self.assertEqual(r["status"],"read")
        self.assertEqual(self.old_low.recover(r["packet"])["status"],"abstain")

    def test_success_has_explicit_signal_verification(self):
        r=self.model.read(self.text)
        self.assertTrue(r["signal_verified"])
        self.assertEqual(r["verification"]["method"],"recover_equals_candidate")
        self.assertEqual(self.model.recover(r["packet"])["meaning"],self.meaning)

    def test_gate_calls_codec_once_without_retries(self):
        with patch.object(self.model,"encode",wraps=self.model.encode) as encode,patch.object(self.model,"recover",wraps=self.model.recover) as recover:
            self.assertEqual(self.model.read(self.text)["status"],"read")
            self.assertEqual(encode.call_count,1)
            self.assertEqual(recover.call_count,1)

    def test_recovery_failure_blocks_read(self):
        with patch.object(self.model,"recover",return_value={"status":"abstain","reason":"injected"}):
            r=self.model.read(self.text)
        self.assertEqual(r["reason"],"meaning_signal_unrecoverable")
        self.assertEqual(r["recovery_reason"],"injected")

    def test_recovered_different_meaning_blocks_read(self):
        other=dict(self.meaning,polarity="polarity:positive")
        with patch.object(self.model,"recover",return_value={"status":"recovered","meaning":other,"residual":0.}):
            r=self.model.read(self.text)
        self.assertEqual(r["reason"],"meaning_signal_mismatch")
        self.assertIsNone(r["packet"])

    def test_actual_wrong_valid_encoded_signal_is_rejected(self):
        wrong=self.model.encode(dict(self.meaning,polarity="polarity:positive"))
        with patch.object(self.model,"encode",return_value=wrong):
            self.assertEqual(self.model.read(self.text)["reason"],"meaning_signal_mismatch")

    def test_failed_read_never_leaks_candidate_or_verified_flag(self):
        r=self.low.read("花子が健太を褒めた。")
        self.assertFalse(r.get("signal_verified",False))
        self.assertNotIn("meaning",r)
        self.assertIsNone(r["packet"])

    def test_verified_flag_cannot_bypass_receiver(self):
        self.assertEqual(self.model.generate(dict(self.packet,signal_verified=True))["status"],"abstain")

    def test_generation_rechecks_post_read_noise(self):
        r=self.model.read(self.text)
        noisy=noisy_packet(r["packet"],.60,"development-noise",self.text)
        self.assertEqual(self.model.generate(noisy)["status"],"abstain")

    def test_model_acceptance_policy_required(self):
        meta=copy.deepcopy(self.model.meta)
        meta.pop("read_acceptance")
        with self.assertRaises(ValueError):
            Model(meta,self.model.memories)

    def test_old_model_cannot_silently_load_as_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            self.old.save(folder)
            with self.assertRaises(ValueError):
                Model.load(folder)

    def test_cross_version_packets_are_rejected(self):
        self.assertEqual(self.model.recover(self.old.encode(self.meaning))["status"],"abstain")
        self.assertEqual(self.old.recover(self.packet)["status"],"abstain")

    def test_numerical_weights_and_payload_unchanged(self):
        self.assertEqual(vector_digest(self.packet),vector_digest(self.old.encode(self.meaning)))
        for name in self.model.memories:
            for a,b in zip(self.model.memories[name].groups,self.old.memories[name].groups):
                np.testing.assert_array_equal(a[1],b[1])

    def test_recover_behavior_unchanged_under_noise(self):
        for level in (0,.05,.15,.30,.60):
            a=noisy_packet(self.packet,level,"dev",self.text)
            b=noisy_packet(self.old.encode(self.meaning),level,"dev",self.text)
            self.assertEqual(self.model.recover(a),self.old.recover(b))

    def test_noise_is_exactly_relative_l2_and_deterministic(self):
        p=noisy_packet(self.packet,.15,"dev",self.text)
        self.assertEqual(p,noisy_packet(self.packet,.15,"dev",self.text))
        v=np.array(self.packet["real"])+1j*np.array(self.packet["imag"])
        w=np.array(p["real"])+1j*np.array(p["imag"])
        self.assertAlmostEqual(np.linalg.norm(w-v)/np.linalg.norm(v),.15,places=12)

    def test_noise_zero_is_copy_and_no_extra_fields(self):
        p=noisy_packet(self.packet,0,"dev",self.text)
        self.assertEqual(p,self.packet)
        self.assertIsNot(p,self.packet)
        self.assertEqual(set(p),set(self.packet))

    def test_invalid_noise_rejected(self):
        for level in (-1,float("nan"),float("inf"),True,".1"):
            with self.assertRaises(ValueError):
                noisy_packet(self.packet,level,"dev",self.text)

    def test_memory_table_control_is_measured(self):
        r=memory_load(512,8,"development-memory")
        self.assertEqual(r["table_reference"]["known_exact"],8)
        self.assertEqual(r["table_reference"]["missing_correct_rejection"],64)
        self.assertEqual(len(r["records"]),72)

    def test_memory_capacity_hard_limit_unchanged(self):
        with self.assertRaises(ValueError):
            fit_memory(Space(Book(128,"dev")),[({"address":str(i)},"x") for i in range(257)],partial=False)

    def test_self_consistency_does_not_prove_semantic_truth(self):
        pairs=copy.deepcopy(train_for(FOLDS[0]))
        for row in pairs:
            m=row["meaning"]
            m["subject"],m["object"]=m["object"],m["subject"]
        model=fit(pairs,data("lexicon"))
        read=model.read(self.text)
        self.assertEqual(read["status"],"read")
        self.assertTrue(read["signal_verified"])
        self.assertNotEqual(model.recover(read["packet"])["meaning"],self.meaning)

    def test_signal_identity_is_not_authentication(self):
        replaced=self.model.encode(dict(self.meaning,polarity="polarity:positive"))
        out=self.model.generate(replaced,"object")
        self.assertEqual(out["status"],"generated")
        self.assertNotEqual(interpret(out["text"]),self.meaning)

    def test_reader_api_has_no_gold_or_external_expectation(self):
        from plm_l1_v05.reader import read
        self.assertEqual(list(inspect.signature(read).parameters),["model","text"])
        self.assertNotIn("evaluation_support",inspect.getsource(read))

    def test_direct_encode_is_construction_not_acceptance(self):
        meaning=interpret("花子が健太を褒めた。")
        p=self.low.encode(meaning)
        self.assertNotIn("signal_verified",p)
        self.assertEqual(self.low.recover(p)["status"],"abstain")


if __name__=="__main__":
    unittest.main()
