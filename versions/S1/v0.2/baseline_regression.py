"""S1 v0.1 numerical subset, retaining the complete historical package unchanged."""
import argparse
import json
from plm_s1_v02 import BASELINE
from plm_p1.core import digest
from plm_p1.__main__ import write_json
from plm_s1.evaluation import trial


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    p=json.loads((BASELINE/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    old=json.loads((BASELINE/'results/EVALUATION_RESULTS.json').read_text(encoding='utf-8'))
    code,channel=41001,52001
    rows,audits=[],[]
    for condition in p['conditions']:
        r=trial((code,channel,condition))
        rows.extend(r['rows']); audits.extend(r['audits'])
    reference=[r for r in old['rows'] if r['code_seed']==code and r['channel_seed']==channel]
    reference_audits=[r for r in old['trial_audits'] if r['code_seed']==code and r['channel_seed']==channel]
    result={'scope':'S1 v0.1: all 12 conditions x 5 methods x one code/channel seed pair, not full old numerical replay',
            'queries':len(rows),'sync_audits':len(audits),'code_seed':code,'channel_seed':channel,
            'exact_reference_match':digest(rows)==digest(reference) and digest(audits)==digest(reference_audits),
            'reference_hash':digest([reference,reference_audits]),'replay_hash':digest([rows,audits])}
    write_json(args.out,result)
    print(json.dumps(result,indent=2))
    if not result['exact_reference_match']: raise SystemExit(1)


if __name__=='__main__': main()
