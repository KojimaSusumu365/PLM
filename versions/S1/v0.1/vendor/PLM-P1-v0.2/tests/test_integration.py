import unittest
from copy import deepcopy
import json
import numpy as np
from plm_p1_v02 import BASELINE
from plm_p1.core import PhaseCodebook,encode,symbol
from plm_p1.adapter import r1_module,from_r1_envelope
from plm_p1_v02.fixtures import public_catalogue,make_frames,entity_candidates,DOC
from plm_p1_v02.recovery import Receiver
from plm_p1_v02.evaluation import protocol


class IntegrationTests(unittest.TestCase):
    def test_protocol_matches_runtime_and_seeds_disjoint(self):
        p=protocol()
        self.assertEqual(len(p["evaluation_code_seeds"])*len(p["evaluation_channel_seeds"]),64)
        old={1101,1102,1103,1104,7101,7102,7103,7104,7105,7106,7107,7108}
        self.assertFalse(old & set(p["evaluation_code_seeds"]))

    def test_public_catalogue_contains_decoys_without_occupancy(self):
        c=public_catalogue()
        self.assertEqual(len(c["addresses"]),8)
        self.assertEqual(sum(len(v) for v in c["vocabulary"].values()),11)
        self.assertTrue(all(set(r)=={"document_id","event_id"} for r in c["addresses"]))

    def test_public_catalogue_does_not_change_with_slot_assignments(self):
        a=public_catalogue()
        frames=make_frames(4)
        frames[0]["slots"],frames[1]["slots"]=frames[1]["slots"],frames[0]["slots"]
        self.assertEqual(a,public_catalogue())

    def test_metadata_never_enters_signal(self):
        frames=make_frames(4)
        book=PhaseCodebook(2048,"metadata-v02")
        before=encode(frames,book)
        frames[0]["metadata"]["gold"]={"misleading":"never passed to decoder"}
        np.testing.assert_array_equal(before,encode(frames,book))

    def test_target_clause_preserved_and_numerically_recoverable(self):
        book=PhaseCodebook(2048,"target-unit-v02")
        frames=make_frames(1)
        target=symbol("clause","S001:C001",DOC)
        frames[0]["slots"]["target_clause"]=target
        r=Receiver(encode(frames,book),None,book,public_catalogue())
        recovered=r.scores(DOC,"event-000","target_clause",[target,symbol("clause","S001:C002",DOC)])
        self.assertEqual(recovered["selected"],target)
        self.assertIs(recovered["eligible_for_inference"],False)

    def test_scoped_entities_do_not_merge(self):
        frames=make_frames(1)
        book=PhaseCodebook(2048,"scope-unit-v02")
        truth=frames[0]["slots"]["subject"]
        other=symbol("entity",truth["id"],"other-document")
        receiver=Receiver(encode(frames,book),None,book,public_catalogue())
        self.assertEqual(receiver.scores(DOC,"event-000","subject",[truth,other])["selected"],truth)


def adapter_case(index):
    def test(self):
        # Frozen known examples, not a blind semantic evaluation corpus.
        cases=json.loads((BASELINE/"examples/R1_ADAPTER_EXAMPLES.json").read_text(encoding="utf-8"))["cases"]
        case=cases[index]
        r1=r1_module()
        actual=from_r1_envelope(r1.export_observations(r1.analyze(case["source_inputs"])))
        self.assertEqual(actual,case["frames"])
        book=PhaseCodebook(2048,"r1-case-v02")
        # Broad fixed catalogue from frozen examples, no current truth injection.
        vocab={}
        for old in cases:
            for f in old["frames"]:
                for role,value in f["slots"].items():
                    if value not in vocab.setdefault(role,[]): vocab[role].append(value)
        empty={"format":"plm-public-nuisance-catalogue-v1","addresses":[],"vocabulary":{}}
        receiver=Receiver(encode(actual,book),None,book,empty)
        for f in actual:
            self.assertIs(f["metadata"]["eligible_for_inference"],False)
            for role,truth in f["slots"].items():
                r=receiver.scores(f["document_id"],f["event_id"],role,vocab[role])
                self.assertEqual(r["selected"],truth)
                self.assertIs(r["eligible_for_inference"],False)
    return test


for i in range(5): setattr(IntegrationTests,f"test_frozen_r1_adapter_case_{i}",adapter_case(i))


if __name__=="__main__": unittest.main()
