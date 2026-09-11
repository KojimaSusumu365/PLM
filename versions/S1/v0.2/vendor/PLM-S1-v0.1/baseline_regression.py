"""Frozen P1 v0.2 numerical regression subset; deliberately not a full old re-evaluation."""
import argparse
import json
from pathlib import Path
from plm_s1 import BASELINE
from plm_p1.core import digest
from plm_p1_v02.experiment import trial
from plm_p1.__main__ import write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    p=json.loads((BASELINE/"evaluation/PROTOCOL.json").read_text(encoding="utf-8"))
    original=json.loads((BASELINE/"results/EVALUATION_RESULTS.json").read_text(encoding="utf-8"))
    code,channel=32001,91001
    rows=[]
    for condition in p["conditions"]:
        r,b=trial(code,channel,condition)
        rows.extend(r)
    reference=[r for r in original["rows"] if r["code_seed"]==code and r["channel_seed"]==channel]
    result={"scope":"P1 v0.2: all 12 conditions x 5 methods, one code/channel seed pair; not full old numerical replay",
            "queries":len(rows),"code_seed":code,"channel_seed":channel,"exact_reference_match":digest(rows)==digest(reference),
            "reference_hash":digest(reference),"replay_hash":digest(rows)}
    write_json(args.out,result)
    print(json.dumps(result,indent=2))
    if not result["exact_reference_match"]: raise SystemExit(1)


if __name__=="__main__": main()
