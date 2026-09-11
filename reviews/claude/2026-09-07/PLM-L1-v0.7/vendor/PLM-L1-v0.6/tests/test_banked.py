import copy
import hashlib
import json
import struct
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import Book,canonical
from plm_l1_v06.banked import (BankedMemory,MemoryBlock,FreshBook,MODES,META_BYTES,CACHE_SLOT_BYTES,CACHE_SLOTS,
                              fit_banked,bank_count,bank_seed,key_code,value_code,route)
from plm_l1_v06.projection import Space,fit_memory
from plm_l1_v06.training import fit
from plm_l1_v06.runtime import Model
from evaluation_support import data,train_for,interpret
from measurements import count,empty_counts
from memory_bench import measure


def observations(n=32):
    return [({"address":"dev:"+str(i)},"label:"+str(i%8)) for i in range(n)]


def make(mode="split_proof",n=32,d=512,cache=0):
    return fit_banked(observations(n),d,"banked-unit-0",partial=False,mode=mode,cache_slots=cache)[0]


class BankedTests(unittest.TestCase):
    def test_exact_budget_all_five_modes(self):
        for d in (128,512,2048):
            sizes=[make(mode,d=d).storage() for mode in MODES]
            self.assertTrue(all(s==sizes[0] for s in sizes))
            self.assertEqual(sizes[0]["state_bytes"],META_BYTES+16*d)

    def test_fixed_cache_budget_after_queries(self):
        memory=make(cache=CACHE_SLOTS)
        before=memory.storage()
        for i in range(128):
            memory.recall({"address":"missing:"+str(i)})
        self.assertEqual(before,memory.storage())
        self.assertEqual(before["cache_capacity_bytes"],CACHE_SLOT_BYTES*CACHE_SLOTS)

    def test_cache_result_mutation_cannot_poison(self):
        m=make(n=8,d=2048,cache=CACHE_SLOTS)
        q=observations(1)[0][0]
        original=m.recall(q)
        expected=copy.deepcopy(original)
        original["value"]="tampered"
        original["projections"][0]["score"]=-99
        self.assertEqual(m.recall(q),expected)

    def test_cache_and_cold_answers_identical(self):
        a,b=make(cache=CACHE_SLOTS),make(cache=0)
        for c,_ in observations()+[({"address":"unknown"},None)]:
            self.assertEqual(a.recall(c),b.recall(c))
            self.assertEqual(a.recall(c),b.recall(c))
        a.clear_cache()
        self.assertFalse(any(a.cache))

    def test_no_persistent_codebook_or_key_table(self):
        m=make()
        self.assertFalse(hasattr(m,"__dict__"))
        self.assertEqual(BankedMemory.__slots__,("blocks","cache"))
        for b in m.blocks:
            self.assertFalse(hasattr(b,"__dict__"))
            self.assertNotIn("dev:",canonical(b.meta()))

    def test_readonly_blob_public_interface(self):
        b=make().blocks[0]
        with self.assertRaises(AttributeError):
            b.blob=b.blob

    def test_banks_adapt_only_to_projected_load_and_budget(self):
        self.assertEqual([bank_count(n,8192,3) for n in (8,9,16,17,32,33,256)],[1,2,2,4,4,8,8])
        self.assertEqual(bank_count(256,128,3),1)
        self.assertEqual(bank_count(256,512,3),4)
        self.assertEqual(bank_count(256,8192,0),1)

    def test_proof_weights_in_total_budget(self):
        for mode in MODES:
            b=make(mode).blocks[0]
            m=b.meta()
            self.assertEqual(m["banks"]*(m["value_width"]+m["proof_width"]),512)
            self.assertEqual(m["proof_width"]>0,mode in ("proof","split_proof","split_unchecked"))

    def test_evidence_ablation_identical_numerical_arrays(self):
        a,b=make("split_proof"),make("split_unchecked")
        self.assertEqual(a.blocks[0].blob[META_BYTES:],b.blocks[0].blob[META_BYTES:])
        for c,_ in observations(128):
            x,y=a.recall(c),b.recall(c)
            self.assertEqual(x["projections"][0]["score"],y["projections"][0]["score"])
            if x["value"] is not None:
                self.assertEqual(x["value"],y["value"])

    def test_single_matches_legacy_value_equations(self):
        obs=observations()
        old,_=fit_memory(Space(Book(512,"banked-unit-0")),obs,partial=False)
        new=make("single")
        np.testing.assert_array_equal(old.groups[0][1],np.frombuffer(new.blocks[0].blob,dtype="<c16",offset=META_BYTES))
        for c,_ in observations(64):
            a,b=old.recall(c),new.recall(c)
            self.assertEqual(a["value"],b["value"])
            self.assertEqual(a["projections"][0]["score"],b["projections"][0]["score"])

    def test_partial_key_routes_novel_combinations(self):
        obs=[({"part":str(i),"nuisance":n},str(i%2)) for i in range(16) for n in ("a","b")]
        memory,stats=fit_banked(obs,8192,"banked-unit-0",cache_slots=0)
        self.assertEqual(stats["masks"],[["part"]])
        self.assertGreater(stats["bank_counts"][0],1)
        for i in range(16):
            a=memory.recall({"part":str(i),"nuisance":"a"})
            b=memory.recall({"part":str(i),"nuisance":"never_seen_combination"})
            self.assertEqual(a,b)
            self.assertEqual(a["value"],str(i%2))
        self.assertIsNone(memory.recall({"part":"unregistered","nuisance":"a"})["value"])

    def test_routing_does_not_use_labels(self):
        obs=observations()
        a,_=fit_banked(obs,512,"banked-unit-0",partial=False)
        b,_=fit_banked([(c,"other:"+t) for c,t in obs],512,"banked-unit-0",partial=False)
        self.assertEqual(a.blocks[0].meta()["counts"],b.blocks[0].meta()["counts"])

    def test_pair_evidence_is_key_and_value_specific(self):
        book=FreshBook(2048,"unit-evidence")
        a=book.code("key_value_pair",[{"x":"a"},"v1"])
        b=book.code("key_value_pair",[{"x":"b"},"v1"])
        c=book.code("key_value_pair",[{"x":"a"},"v2"])
        self.assertLess(abs(np.vdot(a,b).real/2048),.15)
        self.assertLess(abs(np.vdot(a,c).real/2048),.15)

    def test_zero_evidence_rejects_same_value_recall(self):
        block=make(n=8,d=2048).blocks[0]
        m=block.meta()
        v=np.frombuffer(block.blob,dtype="<c16",offset=META_BYTES).copy()
        v[m["value_width"]:]=0
        changed=MemoryBlock(block.blob[:META_BYTES]+v.tobytes())
        self.assertIsNotNone(block.recall(observations(1)[0][0])["value"])
        self.assertIsNone(changed.recall(observations(1)[0][0])["value"])

    def test_wrong_value_not_validated_by_key_only(self):
        obs=[({"address":"first"},"one"),({"address":"second"},"two")]
        mem,_=fit_banked(obs,8192,"unit-pair",partial=False,mode="proof",cache_slots=0)
        b=mem.blocks[0]; m=b.meta()
        v=np.frombuffer(b.blob,dtype="<c16",offset=META_BYTES).copy()
        book=FreshBook(m["value_width"],m["seed"])
        v[:m["value_width"]]=key_code(book,obs[0][0]).conj()*value_code(book,"two")
        r=MemoryBlock(b.blob[:META_BYTES]+v.tobytes()).recall(obs[0][0])
        self.assertGreater(r["score"],.99)
        self.assertLess(r["evidence"],.2)
        self.assertIsNone(r["value"])

    def test_overload_still_has_false_accepts(self):
        m,_=fit_banked(observations(128),128,"banked-development-0",partial=False,cache_slots=0)
        self.assertGreater(sum(m.recall({"address":"absent-dev:"+str(i)})["value"] is not None for i in range(128)),0)

    def test_invalid_dimension_mode_and_cache_rejected(self):
        for kwargs in ({"dimension":192},{"dimension":True},{"mode":[]},{"mode":"unknown"},{"cache_slots":1}):
            options=dict(dimension=512,seed="unit",partial=False)
            options.update(kwargs)
            with self.assertRaises(ValueError):
                fit_banked(observations(),**options)

    def test_missing_query_field_rejected(self):
        with self.assertRaises(ValueError):
            make().recall({})

    def test_invalid_block_padding_length_and_weights(self):
        b=make().blocks[0].blob
        variants=[b[:-1],b[:META_BYTES-1]+b"x"+b[META_BYTES:],b[:META_BYTES]+np.full(512,np.nan,dtype="<c16").tobytes()]
        for blob in variants:
            with self.assertRaises(ValueError):
                MemoryBlock(blob)

    def test_no_query_time_learning_or_adaptation(self):
        m=make()
        before=m.blocks[0].blob
        with patch("plm_l1_v06.banked.dependency_leaves",side_effect=AssertionError()):
            for i in range(100):
                m.recall({"address":"unknown:"+str(i)})
        self.assertEqual(before,m.blocks[0].blob)

    def test_multi_mask_conflicting_values_abstain(self):
        a,_=fit_banked([({"x":"k"},"a")],2048,"unit",cache_slots=0)
        b,_=fit_banked([({"y":"k"},"b")],2048,"unit",cache_slots=0)
        self.assertIsNone(BankedMemory(a.blocks+b.blocks,0).recall({"x":"k","y":"k"})["value"])

    def test_count_denominators(self):
        c=empty_counts(("known","missing"))
        for accepted,exact in ((True,True),(True,False),(False,False)):
            count(c,"known",accepted,exact)
        count(c,"missing",False,False)
        self.assertEqual([c["known_"+k] for k in ("requests","exact","wrong","abstained")],[3,1,1,1])
        self.assertEqual(c["missing_exact"],0)

    def test_benchmark_includes_wrong_and_missing_records(self):
        r,_=measure(128,8,"unit",list(MODES),8)
        for method in r["methods"].values():
            c=method["counts"]
            self.assertEqual(len(method["records"]),16)
            self.assertEqual(c["known_exact"]+c["known_wrong"]+c["known_abstained"],8)
            self.assertEqual(c["missing_accepted"]+c["missing_correct_rejection"],8)


class SignalGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=fit(train_for("object_negative"),data("lexicon"))
        cls.text="花子を太郎が助けなかった。"

    def test_unrecoverable_own_candidate_abstains(self):
        with patch.object(Model,"recover",return_value={"status":"abstain","reason":"unit_failure"}):
            r=self.model.read(self.text)
        self.assertEqual(r["reason"],"meaning_signal_unrecoverable")
        self.assertIsNone(r["packet"])

    def test_different_recovered_meaning_abstains(self):
        m=interpret(self.text)
        m["subject"],m["object"]=m["object"],m["subject"]
        with patch.object(Model,"recover",return_value={"status":"recovered","meaning":m}):
            r=self.model.read(self.text)
        self.assertEqual(r["reason"],"meaning_signal_mismatch")

    def test_inference_cannot_use_training_selector(self):
        with patch("plm_l1_v06.banked.dependency_leaves",side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.model.read(self.text)["packet"])["text"],self.text)

    def test_language_fixed_memory_budget(self):
        sizes=[]
        for mode in MODES:
            m=fit(train_for("object_negative"),data("lexicon"),memory_mode=mode)
            sizes.append(sum(mem.storage()["owned_heap_bytes"] for mem in m.memories.values()))
        self.assertEqual(len(set(sizes)),1)


if __name__=="__main__":
    unittest.main()
