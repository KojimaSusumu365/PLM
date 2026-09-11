import copy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from plm_l1_v06.algebra import Book,canonical
from plm_l1_v06.lexicon import tokenize,GOALS
from plm_l1_v06.features import observations,role_context,shape
from plm_l1_v06.projection import Space,dependency_leaves,fit_memory
from plm_l1_v06.training import fit
from plm_l1_v06.runtime import Model
from evaluation_support import data,train_for,FOLDS,heldout,text_goal,interpret,INVALID,OldSS,PartialTable,OldTable,opaque,normalize_markers
from measurements import bad_packets


class InheritedPartsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lex=data("lexicon")
        cls.models={fold:fit(train_for(fold),cls.lex) for fold in FOLDS}
        cls.model=cls.models[FOLDS[0]]
        cls.text="花子を太郎が助けなかった。"
        cls.meaning=interpret(cls.text)
        cls.packet=cls.model.encode(cls.meaning)

    def test_all_folds_development_reading(self):
        for fold,model in self.models.items():
            for row in data("development"):
                with self.subTest(fold=fold,text=row["text"]):
                    r=model.read(row["text"])
                    self.assertEqual(r["status"],"read")
                    self.assertEqual(model.recover(r["packet"])["meaning"],row["meaning"])

    def test_all_folds_development_generation(self):
        for model in self.models.values():
            for row in data("development"):
                for goal in GOALS:
                    out=model.generate(model.encode(row["meaning"]),goal)
                    self.assertEqual(interpret(out["text"]),row["meaning"])
                    self.assertEqual(text_goal(out["text"]),goal)

    def test_novel_roundtrip_all_folds(self):
        for fold,model in self.models.items():
            for row in data("development"):
                goal=text_goal(row["text"])
                if heldout(row["meaning"],goal,fold):
                    out=model.generate(model.read(row["text"])["packet"],goal)
                    self.assertEqual(out["text"],row["text"])

    def test_entire_cell_excluded(self):
        for fold in FOLDS:
            train=train_for(fold)
            self.assertEqual(len(train),432)
            self.assertFalse(any(heldout(r["meaning"],text_goal(r["text"]),fold) for r in train))
            self.assertEqual(sum(heldout(r["meaning"],text_goal(r["text"]),fold) for r in data("evaluation")),48)

    def test_components_and_tokens_are_known(self):
        kinds={t["surface"]:t["kind"] for t in self.lex["tokens"]}
        for fold in FOLDS:
            train=train_for(fold)
            test=[r for r in data("evaluation") if heldout(r["meaning"],text_goal(r["text"]),fold)]
            a,b=observations(train,self.lex),observations(test,self.lex)
            self.assertLessEqual({(c["anchor"],t) for c,t in b["gaps"]},{(c["anchor"],t) for c,t in a["gaps"]})
            self.assertLessEqual({t for r in test for t in tokenize(r["text"],kinds)},{t for r in train for t in tokenize(r["text"],kinds)})

    def test_lexical_composition_split_stays_disjoint(self):
        keys=lambda rows:{tuple(r["meaning"][s] for s in ("subject","object","predicate")) for r in rows}
        a,b,c=[keys(data(s)) for s in ("train","development","evaluation")]
        self.assertFalse(a&b or a&c or b&c)

    def test_old_ss_matched_training_control(self):
        old=OldSS(train_for(FOLDS[0]),self.lex,"parts-development-0")
        self.assertEqual(old.meta["pair_count"],432)
        self.assertEqual(old.read(self.text)["status"],"abstain")
        self.assertEqual(old.generate(old.encode(self.meaning),"object")["status"],"abstain")
        known="太郎が花子を助けなかった。"
        self.assertEqual(old.read(known)["status"],"read")
        self.assertEqual(old.generate(old.encode(self.meaning),"subject")["text"],known)

    def test_full_context_control_preserves_seen(self):
        full=fit(train_for(FOLDS[0]),self.lex,partial=False)
        for row in data("development"):
            goal=text_goal(row["text"])
            is_novel=heldout(row["meaning"],goal,FOLDS[0])
            self.assertEqual(full.read(row["text"])["status"],"abstain" if is_novel else "read")
            self.assertEqual(full.generate(full.encode(row["meaning"]),goal)["status"],"abstain" if is_novel else "generated")

    def test_no_learning_keeps_lexical_prior(self):
        model=fit(train_for(FOLDS[0]),self.lex,learning=False)
        self.assertEqual(model.memories["lexical_read"].recall({"surface":"太郎"})["value"],"entity:太郎")
        self.assertEqual(model.read(self.text)["status"],"abstain")
        self.assertEqual(model.generate(model.encode(self.meaning))["status"],"abstain")

    def test_partial_table_is_successful_too(self):
        model=PartialTable(train_for(FOLDS[0]),self.lex)
        self.assertEqual(model.read(self.text)["status"],"read")
        self.assertEqual(model.generate(model.encode(self.meaning))["text"],self.text)

    def test_old_table_cannot_reuse(self):
        model=OldTable(train_for(FOLDS[0]),self.lex)
        self.assertEqual(model.read(self.text)["status"],"abstain")
        self.assertEqual(model.generate(model.encode(self.meaning))["status"],"abstain")

    def test_typed_feature_bindings_do_not_alias(self):
        space=Space(Book())
        self.assertGreater(np.linalg.norm(space.key({"goal":"subject","anchor":"object"})-space.key({"goal":"object","anchor":"subject"})),1.)

    def test_sequence_order_preserved(self):
        space=Space(Book())
        self.assertGreater(np.linalg.norm(space.target(canonical(["subject","object"]))-space.target(canonical(["object","subject"]))),1.)

    def test_dependencies_are_learned_not_supplied(self):
        for model in self.models.values():
            stats=model.meta["statistics"]
            self.assertNotIn("whole_shape",{f for m in stats["roles"]["masks"] for f in m})
            self.assertNotIn("goal",{f for m in stats["gaps"]["masks"] for f in m})
            self.assertEqual(stats["modality"]["masks"],[["leading_markers"]])
        self.assertEqual(list(inspect.signature(fit).parameters),["pairs","lexicon","seed","dimension","partial","learning","memory_mode"])

    def test_dependency_can_retain_goal_when_data_requires_it(self):
        pairs=copy.deepcopy(data("train"))
        for row in pairs:
            if text_goal(row["text"])=="object":
                p=row["meaning"]["polarity"]
                row["meaning"]["polarity"]="polarity:positive" if p=="polarity:negative" else "polarity:negative"
        model=fit(pairs,self.lex)
        self.assertIn("goal",{f for mask in model.meta["statistics"]["gaps"]["masks"] for f in mask})
        out=model.generate(model.encode(interpret("太郎が花子を助けた。")),"object")
        self.assertEqual(out["text"],"花子を太郎が助けなかった。")

    def test_projection_selector_independent_example(self):
        obs=[({"relevant":r,"nuisance":n},r) for r in ("a","b") for n in ("x","y")]
        leaves=dependency_leaves(obs)
        self.assertTrue(all(set(c)=={"relevant"} for c,_ in leaves))
        memory,_=fit_memory(Space(Book()),obs)
        self.assertEqual(memory.recall({"relevant":"a","nuisance":"never_seen"})["value"],"a")

    def test_positive_only_support_not_universal(self):
        obs=[({"x":"known"},"supported")]
        self.assertEqual(dependency_leaves(obs),obs)
        memory,_=fit_memory(Space(Book()),obs)
        self.assertIsNone(memory.recall({"x":"unknown"})["value"])

    def test_no_runtime_tree_or_leaf_table(self):
        for mem in self.model.memories.values():
            self.assertFalse(hasattr(mem,"leaves") or hasattr(mem,"tree"))
        serialized=canonical(self.model.meta)
        self.assertTrue(all(row["text"] not in serialized for row in train_for(FOLDS[0])))

    def test_pair_only_api(self):
        for field in ("goal","order","fold","heldout","actions","states","trace","roles"):
            with self.assertRaises(ValueError):
                fit([dict(train_for(FOLDS[0])[0],**{field:[]})],self.lex)

    def test_opaque_markers(self):
        pairs,lex,mapping=opaque(train_for(FOLDS[0]),self.lex)
        model=fit(pairs,lex)
        text=normalize_markers(self.text,mapping)
        self.assertEqual(model.recover(model.read(text)["packet"])["meaning"],self.meaning)
        self.assertEqual(model.generate(model.encode(self.meaning))["text"],text)

    def test_counterfactual_role_labels(self):
        pairs=copy.deepcopy(train_for(FOLDS[0]))
        for row in pairs:
            m=row["meaning"]
            m["subject"],m["object"]=m["object"],m["subject"]
        model=fit(pairs,self.lex)
        expected=dict(self.meaning,subject=self.meaning["object"],object=self.meaning["subject"])
        self.assertEqual(model.recover(model.read(self.text)["packet"])["meaning"],expected)

    def test_ambiguous_alignment_rejected(self):
        text="太郎が太郎を助けた。"
        with self.assertRaises(ValueError):
            fit([{"text":text,"meaning":interpret(text)}],self.lex)

    def test_conflicting_labels_rejected(self):
        rows=copy.deepcopy(train_for(FOLDS[0])[:1])
        other=copy.deepcopy(rows[0])
        other["meaning"]["subject"],other["meaning"]["object"]=other["meaning"]["object"],other["meaning"]["subject"]
        with self.assertRaises(ValueError):
            fit(rows+[other],self.lex)

    def test_marker_semantics_prohibited(self):
        lex=copy.deepcopy(self.lex)
        next(t for t in lex["tokens"] if t["kind"]=="marker")["value"]="negative"
        with self.assertRaises(ValueError):
            fit(train_for(FOLDS[0]),lex)

    def test_invalid_texts_all_folds(self):
        for model in self.models.values():
            for text in INVALID:
                self.assertEqual(model.read(text)["status"],"abstain")

    def test_mismatched_parts_rejected(self):
        for text in ("もし太郎が花子を助けた。","太郎が花子を助けたら。","花子が太郎が助けなかった。","花子を太郎が助けなかった。。"):
            self.assertEqual(self.model.read(text)["status"],"abstain")

    def test_unlearned_role_order_rejected(self):
        self.assertEqual(self.model.read("助けた。花子を太郎が")["status"],"abstain")

    def test_unknown_vocabulary_rejected(self):
        self.assertEqual(self.model.read("未知が花子を助けた。")["status"],"abstain")
        with self.assertRaises(ValueError):
            self.model.encode(dict(self.meaning,subject="entity:未知"))

    def test_missing_parts_not_reconstructed_from_gold(self):
        self.assertEqual(self.model.read("花子を助けなかった。")["status"],"abstain")

    def test_self_reference_inference(self):
        text="太郎が太郎を助けなかった。"
        result=self.model.read(text)
        self.assertEqual(self.model.recover(result["packet"])["meaning"],interpret(text))

    def test_signal_only_packet(self):
        self.assertEqual(set(self.packet),{"schema","model_fingerprint","dimension","real","imag","eligible_for_inference"})
        self.assertNotIn("太郎",canonical(self.packet))

    def test_invalid_packets(self):
        for p in bad_packets(self.model,self.meaning):
            self.assertEqual(self.model.generate(p)["status"],"abstain")

    def test_extra_packet_fields(self):
        for field in ("gold","trace","source","order","parts"):
            self.assertEqual(self.model.generate(dict(self.packet,**{field:[]}))["status"],"abstain")

    def test_nonobject_packets_and_text(self):
        for value in (None,[],1,True):
            self.assertEqual(self.model.generate(value)["status"],"abstain")
            self.assertEqual(self.model.read(value)["status"],"abstain")

    def test_unknown_goal(self):
        for goal in (None,"essay",[]):
            self.assertEqual(self.model.generate(self.packet,goal)["status"],"abstain")

    def test_inference_disabled(self):
        for output in (self.packet,self.model.read(self.text),self.model.generate(self.packet),self.model.recover(self.packet)):
            self.assertFalse(output["eligible_for_inference"])

    def test_generator_never_calls_reader(self):
        with patch.object(Model,"read",side_effect=AssertionError("reader forbidden")):
            self.assertEqual(self.model.generate(self.packet)["text"],self.text)

    def test_no_old_teacher_or_model_calls(self):
        import plm_l1.teacher as teacher
        from plm_l1_v03.runtime import Writer
        from plm_l1_v02.runtime import PairReader
        with patch.object(teacher,"reader_trace",side_effect=AssertionError()),patch.object(teacher,"writer_trace",side_effect=AssertionError()),patch.object(Writer,"generate",side_effect=AssertionError()),patch.object(PairReader,"read",side_effect=AssertionError()):
            model=fit(train_for(FOLDS[0]),self.lex)
            self.assertEqual(model.generate(model.read(self.text)["packet"])["text"],self.text)

    def test_save_load(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            model=Model.load(directory)
            self.assertEqual(model.fingerprint,self.model.fingerprint)
            self.assertEqual(model.generate(self.packet),self.model.generate(self.packet))

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            with self.assertRaises(ValueError):
                self.model.save(directory)

    def test_metadata_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            p=Path(directory)/"model.json"
            info=json.loads(p.read_text(encoding="utf-8"))
            info["metadata"]["pair_count"]+=1
            p.write_text(json.dumps(info),encoding="utf-8")
            with self.assertRaises(ValueError):
                Model.load(directory)

    def test_weight_tampering_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.model.save(directory)
            p=Path(directory)/"weights.npz"
            with np.load(p,allow_pickle=False) as a:
                values={k:a[k] for k in a.files}
            next(iter(values.values()))[0]+=1
            np.savez_compressed(p,**values)
            with self.assertRaises(ValueError):
                Model.load(directory)

    def test_deterministic_pair_order(self):
        model=fit(list(reversed(train_for(FOLDS[0]))),self.lex)
        self.assertEqual(model.fingerprint,self.model.fingerprint)

    def test_duplicate_examples_do_not_inflate_weights(self):
        model=fit(train_for(FOLDS[0])*2,self.lex)
        for name in model.memories:
            for a,b in zip(model.memories[name].blocks,self.model.memories[name].blocks):
                self.assertEqual(a.blob,b.blob)

    def test_invalid_fit_settings(self):
        for kwargs in ({"partial":1},{"learning":0},{"dimension":129},{"seed":""}):
            with self.assertRaises(ValueError):
                fit(train_for(FOLDS[0]),self.lex,**kwargs)

    def test_no_hidden_japanese_grammar(self):
        from plm_l1_v06 import training,reader,runtime,features,projection
        for module in (training,reader,runtime,features,projection):
            code=inspect.getsource(module)
            for text in ("太郎","花子","もし","なかった",'"が"','"を"',"from evaluation_support","import plm_l1_v03","import plm_l1_v02"):
                self.assertNotIn(text,code)


if __name__=="__main__":
    unittest.main()
