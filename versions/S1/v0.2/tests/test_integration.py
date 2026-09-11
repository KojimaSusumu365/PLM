import unittest
from dataclasses import replace
import json
import numpy as np
import plm_s1_v02
from plm_p1.core import PhaseCodebook,encode,digest,symbol
from plm_p1.adapter import from_r1_envelope,r1_module
from plm_p1_v02 import BASELINE as P1_V01
from plm_p1_v02.fixtures import make_frames,public_catalogue,DOC
from plm_s1_v02.link import Link,transmit,spreading_codes,simulate_channel
from plm_s1_v02.packet import to_packet
from plm_s1_v02.receiver import Session
from plm_s1_v02.evaluation import protocol


class IntegrationTests(unittest.TestCase):
    def test_equal_energy_no_free_awgn_gain(self):
        book=PhaseCodebook(2048,"noise-energy-unit")
        values=encode(make_frames(4),book)
        link=Link()
        variances=[]
        for mode in ("direct_sparse","repeat","spread"):
            cfg=replace(link,mode=mode)
            _,norm=transmit(values,book,cfg)
            codes=spreading_codes(book,cfg)
            weights=np.sqrt(4)*codes/(norm["payload_gain"]*np.sum(codes**2,axis=1)[:,None])
            variances.append(np.sum(abs(weights)**2,axis=1))
        for variance in variances[1:]: np.testing.assert_allclose(variance,variances[0],rtol=1e-12,atol=1e-12)

    def test_explicit_spreading_changes_discrete_spectrum(self):
        book=PhaseCodebook(2048,"spectrum-unit")
        values=encode(make_frames(4),book)
        fractions=[]
        for mode in ("repeat","spread"):
            link=Link(mode=mode)
            y,_=transmit(values,book,link)
            payload=y[link.data_indices]
            power=abs(np.fft.fft(payload))**2
            outside=abs(np.fft.fftfreq(len(payload)))>1/8
            fractions.append(float(power[outside].sum()/power.sum()))
        self.assertGreater(fractions[1],fractions[0]+.2)

    def test_protocol_seeds_and_budget(self):
        p=protocol()
        self.assertEqual(len(p["evaluation_code_seeds"])*len(p["evaluation_channel_seeds"]),32)
        self.assertEqual(Link(**p["link"]).frame_length,p["frame_chips"])
        self.assertFalse(set(p["evaluation_code_seeds"])&set(range(32001,32017)))

    def test_revision_target_clause_roundtrip(self):
        book=PhaseCodebook(2048,"s1-revision-unit")
        frames=make_frames(1)
        target=symbol("clause","S001:C001",DOC)
        frames[0]["slots"]["target_clause"]=target
        link=Link()
        tx,norm=transmit(encode(frames,book),book,link)
        y,m=simulate_channel(tx,link,seed=12,delay_chips=4,phase_rad=1.2,cfo_hz=1.1)
        packet=to_packet(y,m,book,link,norm,source_digest=digest(frames))
        session=Session(packet,public_catalogue(),expected_book=book,expected_link=link)
        r=session.query({"document_id":DOC,"event_id":"event-000","role":"target_clause","candidates":[target,symbol("clause","S001:C002",DOC)]})
        self.assertEqual(r["selected"],target)
        self.assertIs(r["eligible_for_inference"],False)


def r1_case(index):
    def test(self):
        cases=json.loads((P1_V01/"examples/R1_ADAPTER_EXAMPLES.json").read_text(encoding="utf-8"))["cases"]
        case=cases[index]
        r1=r1_module()
        frames=from_r1_envelope(r1.export_observations(r1.analyze(case["source_inputs"])))
        self.assertEqual(frames,case["frames"])
        book=PhaseCodebook(2048,"s1-r1-integration-unit")
        link=Link()
        tx,norm=transmit(encode(frames,book),book,link)
        y,m=simulate_channel(tx,link,seed=713,delay_chips=-7,phase_rad=-2.0,cfo_hz=1.09,keep_fraction=.25,noise_std=.25)
        packet=to_packet(y,m,book,link,norm,source_digest=digest(frames))
        vocab={}
        for old in cases:
            for f in old["frames"]:
                for role,value in f["slots"].items():
                    if value not in vocab.setdefault(role,[]): vocab[role].append(value)
        session=Session(packet,{"format":"plm-public-nuisance-catalogue-v1","addresses":[],"vocabulary":{}},expected_book=book,expected_link=link)
        for f in frames:
            for role,truth in f["slots"].items():
                r=session.query({"document_id":f["document_id"],"event_id":f["event_id"],"role":role,"candidates":vocab[role]})
                self.assertEqual(r["selected"],truth)
                self.assertIs(r["eligible_for_inference"],False)
    return test


for i in range(5): setattr(IntegrationTests,f"test_frozen_r1_case_{i}",r1_case(i))


if __name__=="__main__": unittest.main()


