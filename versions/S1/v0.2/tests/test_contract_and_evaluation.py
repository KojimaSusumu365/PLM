import json
from pathlib import Path
import unittest
import numpy as np
import plm_s1_v02
from plm_p1.core import digest
from plm_s1_v02.evaluation import protocol,sync_cases,lock_audit
from plm_s1_v02.packet import from_packet
from plm_s1_v02.receiver import Session,THRESHOLDS
from test_v02 import BOOK,LINK,TX,NORM,CAT,packet,query

ROOT=Path(__file__).resolve().parents[1]


class ContractAndEvaluationTests(unittest.TestCase):
    def test_layout_design_reproducible_selection(self):
        r=json.loads((ROOT/'evaluation/PILOT_LAYOUT_SEARCH.json').read_text(encoding='utf-8'))
        expected=min((c for c in r['candidates'] if c['near_sidelobe_max']<=.80),key=lambda c:(c['far_sidelobe_max'],c['starts']))
        self.assertEqual(r['candidate_count'],837)
        self.assertEqual(r['selected'],expected)
        self.assertEqual(expected['starts'],list(LINK.pilot_starts))

    def test_protocol_thresholds_and_seeds(self):
        p=protocol()
        self.assertEqual(p['thresholds'],THRESHOLDS)
        for kind in ('code','channel'):
            self.assertFalse(set(p['development_'+kind+'_seeds'])&set(p['evaluation_'+kind+'_seeds']))

    def test_impossible_alias_is_explicit_not_hidden(self):
        cases=sync_cases(protocol())
        alias=next(c for c in cases if c.get('frequency_hz')==8000.1)
        self.assertEqual(alias['category'],'sampling_alias_limitation')
        self.assertEqual(next(c for c in cases if c['name']=='pilot_only')['category'],'authentication_limitation')

    def test_wrong_lock_not_same_as_aligned(self):
        s={'status':'aligned','estimated_delay_chips':0,'estimated_cfo_hz':.1,'estimated_phase_rad':0.}
        self.assertTrue(lock_audit(s,{'delay_chips':0,'cfo_hz':1.061538,'phase_rad':0.})['wrong_lock'])
        self.assertFalse(lock_audit(s,{'delay_chips':0,'cfo_hz':.1,'phase_rad':0.})['wrong_lock'])

    def test_pilot_only_does_not_recover_payload(self):
        y=TX.copy()
        y[LINK.data_indices]=0
        s=Session(packet(y),CAT,expected_book=BOOK,expected_link=LINK)
        self.assertEqual(s.synchronization['status'],'aligned')
        r=s.query(query())
        self.assertIsNone(r['selected'])
        self.assertIs(r['eligible_for_inference'],False)

    def test_time_axis_bool_rejected(self):
        p=packet()
        p['time_axis']['sample_count']=True
        p['payload_hash']=digest({k:v for k,v in p.items() if k!='payload_hash'})
        with self.assertRaises(ValueError): from_packet(p)

    def test_bad_query_fields_rejected(self):
        s=Session(packet(),CAT,expected_book=BOOK,expected_link=LINK)
        for field in ('gold','true_phase_rad','channel_seed'):
            with self.subTest(field=field),self.assertRaises(ValueError): s.query(dict(query(),**{field:0}))

    def test_codebook_fingerprint_rejected(self):
        p=packet()
        p['codebook_fingerprint']='0'*64
        p['payload_hash']=digest({k:v for k,v in p.items() if k!='payload_hash'})
        with self.assertRaises(ValueError): from_packet(p)


if __name__=='__main__': unittest.main()
