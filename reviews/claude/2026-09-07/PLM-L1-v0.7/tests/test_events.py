import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import canonical
from plm_l1_v06.runtime import Model as ComponentModel
from plm_l1_v06.lexicon import ROLES
from plm_l1_v07.runtime import EventModel,PACKET_FIELDS
from plm_l1_v07.training import fit
from evaluation_support import data,GOAL_PAIRS,parse_document,document_goals,render,V06
from measurements import INVALID_TEXTS,bad_packets,unique_rows,confusion,count_rows


class EventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=fit(data("folds/object_negative/train"),data("lexicon"))
        cls.rows=data("events_development")
        cls.meaning={"events":[{"subject":"entity:太郎","object":"entity:花子","predicate":"predicate:help","polarity":"polarity:positive","modality":"modality:asserted"},
                               {"subject":"entity:花子","object":"entity:太郎","predicate":"predicate:help","polarity":"polarity:negative","modality":"modality:asserted"}]}
        cls.text="太郎が花子を助けた。花子が太郎を助けなかった。"
        cls.packet=cls.model.encode(cls.meaning)

    def test_all_development_documents_read(self):
        for row in self.rows:
            out=self.model.read(row["text"])
            self.assertEqual(out["status"],"read",row["id"])
            self.assertEqual(self.model.recover(out["packet"])["meaning"],row["meaning"])

    def test_all_development_meanings_all_goal_pairs(self):
        for row in unique_rows("development"):
            for goals in GOAL_PAIRS:
                out=self.model.generate(self.model.encode(row["meaning"]),goals)
                self.assertEqual(parse_document(out["text"]),row["meaning"])
                self.assertEqual(document_goals(out["text"]),goals)

    def test_role_reversal_and_negative_scope(self):
        out=self.model.generate(self.model.read(self.text)["packet"],["object","object"])
        self.assertEqual(out["text"],"花子を太郎が助けた。太郎を花子が助けなかった。")

    def test_modality_stays_with_its_event(self):
        text="もし太郎が花子を助けたら。花子が太郎を助けなかった。"
        r=self.model.read(text)
        out=self.model.generate(r["packet"],["subject","object"])
        self.assertEqual(out["text"],"もし太郎が花子を助けたら。太郎を花子が助けなかった。")

    def test_identical_mentions_not_deduplicated(self):
        m={"events":[self.meaning["events"][0]]*2}
        out=self.model.generate(self.model.encode(m))
        self.assertEqual(out["text"],"太郎が花子を助けた。太郎が花子を助けた。")

    def test_event_order_is_preserved(self):
        m={"events":list(reversed(self.meaning["events"]))}
        out=self.model.generate(self.model.encode(m))
        self.assertEqual(parse_document(out["text"]),m)
        self.assertNotEqual(out["text"],self.text)

    def test_event_binding_distinguishes_swapped_events(self):
        c=self.model.codec
        self.assertFalse(np.array_equal(c.encode(self.meaning),c.encode({"events":list(reversed(self.meaning["events"]))})))

    def test_unbound_control_loses_order_exactly(self):
        m=EventModel(self.model.component,mode="unbound")
        self.assertTrue(np.array_equal(m.codec.encode(self.meaning),m.codec.encode({"events":list(reversed(self.meaning["events"]))})))

    def test_partitioned_control_same_numeric_budget(self):
        m=EventModel(self.model.component,mode="partitioned")
        self.assertEqual(m.codec.encode(self.meaning).nbytes,self.model.codec.encode(self.meaning).nbytes)
        self.assertEqual(m.recover(m.encode(self.meaning))["meaning"],self.meaning)

    def test_absent_second_event_rejected(self):
        c=self.model.codec; event=self.meaning["events"][0]
        v=c.presence[0].copy()
        for role in ROLES:
            v+=c.codes[0][role][c.candidates[role].index(event[role])]
        v*=c.scale
        p=dict(self.packet,real=v.real.tolist(),imag=v.imag.tolist())
        self.assertEqual(self.model.recover(p)["status"],"abstain")

    def test_numeric_packet_has_no_event_list_or_subpackets(self):
        self.assertEqual(set(self.packet),PACKET_FIELDS)
        self.assertEqual(len(self.packet["real"]),8192)
        self.assertEqual(len(self.packet["imag"]),8192)
        self.assertNotIn("太郎",canonical(self.packet))
        self.assertNotIn("events",canonical(self.packet))

    def test_bad_packets_rejected(self):
        for packet in bad_packets(self.model,self.meaning):
            self.assertEqual(self.model.generate(packet)["status"],"abstain")

    def test_cross_model_packet_rejected(self):
        for other in (EventModel(self.model.component,seed="another"),EventModel(self.model.component,mode="partitioned")):
            self.assertEqual(other.generate(self.packet)["reason"],"packet_model_mismatch")

    def test_old_single_event_packet_rejected(self):
        p=self.model.component.encode(self.meaning["events"][0])
        self.assertEqual(self.model.generate(p)["status"],"abstain")

    def test_packet_extra_gold_source_hint_rejected(self):
        for field in ("events","source","meaning","event_hints","subpackets","gold"):
            self.assertEqual(self.model.generate(dict(self.packet,**{field:self.meaning}))["status"],"abstain")

    def test_bad_event_count_and_fields(self):
        for meaning in (None,[],{},self.meaning["events"],{"events":[]},{"events":self.meaning["events"][:1]},
                        {"events":self.meaning["events"]+[self.meaning["events"][0]]},dict(self.meaning,order=[0,1])):
            with self.assertRaises(ValueError):
                self.model.encode(meaning)

    def test_unknown_semantic_value_rejected(self):
        m=copy.deepcopy(self.meaning); m["events"][1]["subject"]="entity:未知"
        with self.assertRaises(ValueError):
            self.model.encode(m)

    def test_input_not_mutated(self):
        m=copy.deepcopy(self.meaning)
        self.model.encode(m)
        self.assertEqual(m,self.meaning)
        p=copy.deepcopy(self.packet)
        self.model.generate(p)
        self.assertEqual(p,self.packet)

    def test_invalid_documents_rejected(self):
        for text in INVALID_TEXTS+(None,[],True,1):
            self.assertEqual(self.model.read(text)["status"],"abstain")

    def test_only_between_sentence_whitespace_allowed(self):
        out=self.model.read("太郎が花子を助けた。\n花子が太郎を助けなかった。")
        self.assertEqual(self.model.recover(out["packet"])["meaning"],self.meaning)
        self.assertEqual(self.model.read("太郎 が花子を助けた。花子が太郎を助けなかった。")["status"],"abstain")

    def test_bad_goals_rejected(self):
        for goals in (None,"subject",[],["subject"],["subject"]*3,["subject","essay"],["subject",[]]):
            self.assertEqual(self.model.generate(self.packet,goals)["status"],"abstain")

    def test_no_partial_generation_on_second_event_failure(self):
        with patch.object(self.model.component,"generate",side_effect=[{"status":"generated","text":"first"},{"status":"abstain","reason":"unit_failure"}]):
            out=self.model.generate(self.packet)
        self.assertEqual(out["status"],"abstain")
        self.assertIsNone(out["text"])

    def test_no_partial_packet_on_second_event_failure(self):
        out=self.model.read("太郎が花子を助けた。彼が太郎を助けた。")
        self.assertEqual(out["status"],"abstain")
        self.assertIsNone(out["packet"])

    def test_reader_requires_recoverable_shared_signal(self):
        with patch.object(EventModel,"recover",return_value={"status":"abstain","meaning":None}):
            out=self.model.read(self.text)
        self.assertEqual(out["reason"],"two_event_signal_unrecoverable")
        self.assertIsNone(out["packet"])

    def test_reader_requires_both_candidate_matches(self):
        wrong={"events":list(reversed(self.meaning["events"]))}
        with patch.object(EventModel,"recover",return_value={"status":"recovered","meaning":wrong}):
            out=self.model.read(self.text)
        self.assertEqual(out["reason"],"two_event_signal_mismatch")

    def test_generation_never_calls_reader(self):
        with patch.object(EventModel,"read",side_effect=AssertionError()),patch.object(ComponentModel,"read",side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.packet)["text"],self.text)

    def test_no_runtime_feature_learning_or_oracle(self):
        with patch("plm_l1_v06.banked.dependency_leaves",side_effect=AssertionError()),patch("plm_l1.teacher.surface",side_effect=AssertionError()):
            self.assertEqual(self.model.generate(self.model.read(self.text)["packet"])["text"],self.text)

    def test_no_learning_ablation(self):
        m=fit(data("folds/object_negative/train"),data("lexicon"),learning=False)
        self.assertEqual(m.read(self.text)["status"],"abstain")
        self.assertEqual(m.generate(m.encode(self.meaning))["status"],"abstain")

    def test_component_primary_weights_unchanged(self):
        old=ComponentModel.load(V06/"results"/"model")
        self.assertEqual(old.fingerprint,self.model.component.fingerprint)
        for name,memory in old.memories.items():
            for a,b in zip(memory.blocks,self.model.component.memories[name].blocks):
                self.assertEqual(a.blob,b.blob)

    def test_two_event_binding_is_explicitly_not_learned(self):
        self.assertEqual(self.model.meta["binding_learning"],"designed_not_learned")
        self.assertEqual(self.model.component.meta["pair_count"],432)

    def test_inference_remains_disabled(self):
        for out in (self.packet,self.model.read(self.text),self.model.generate(self.packet),self.model.recover(self.packet)):
            self.assertIs(out["eligible_for_inference"],False)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            m=EventModel.load(directory)
            self.assertEqual(m.fingerprint,self.model.fingerprint)
            self.assertEqual(m.generate(self.packet),self.model.generate(self.packet))

    def test_save_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            with self.assertRaises(ValueError):
                self.model.save(directory)

    def test_metadata_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            p=Path(directory)/"model.json"; info=json.loads(p.read_text(encoding="utf-8"))
            info["metadata"]["event_positions"]="causal_order"
            p.write_text(json.dumps(info),encoding="utf-8")
            with self.assertRaises(ValueError):
                EventModel.load(directory)

    def test_invalid_codec_config(self):
        for kwargs in ({"dimension":64},{"dimension":192},{"seed":""},{"mode":"unknown"},{"mode":[]}):
            with self.assertRaises(ValueError):
                EventModel(self.model.component,**kwargs)

    def test_development_and_evaluation_pairs_disjoint(self):
        a={canonical(r["meaning"]) for r in self.rows}
        b={canonical(r["meaning"]) for r in data("events_evaluation")}
        self.assertEqual((len(a),len(b),len(a&b)),(72,72,0))

    def test_all_nine_categories_and_four_goal_pairs(self):
        for split in ("development","evaluation"):
            rows=data("events_"+split)
            self.assertEqual(len(rows),288)
            self.assertEqual(len({r["category"] for r in rows}),9)
            self.assertTrue(all(parse_document(r["text"])==r["meaning"] for r in rows))

    def test_order_error_not_hidden_by_bag_scoring(self):
        wrong={"events":list(reversed(self.meaning["events"]))}
        self.assertTrue(confusion(wrong,self.meaning)["event_swapped"])
        self.assertGreater(confusion(wrong,self.meaning)["cross_event_slots"],0)

    def test_valid_semantic_change_is_not_authentication(self):
        other=copy.deepcopy(self.meaning); other["events"][1]["polarity"]="polarity:positive"
        out=self.model.generate(self.model.encode(other))
        self.assertEqual(parse_document(out["text"]),other)
        self.assertNotEqual(parse_document(out["text"]),self.meaning)

    def test_count_keeps_wrong_and_abstention_separate(self):
        rows=[{"stage":"read","accepted":True,"exact":True},{"stage":"read","accepted":True,"exact":False},{"stage":"read","accepted":False,"exact":False}]
        self.assertEqual(count_rows(rows)["read"],{"requests":3,"accepted":2,"exact":1,"wrong":1,"abstained":1})


if __name__=="__main__":
    unittest.main()
