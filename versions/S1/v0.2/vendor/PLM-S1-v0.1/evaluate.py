import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
os.environ.setdefault("OMP_NUM_THREADS","1")
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from plm_s1.evaluation import run_suite,render_report,protocol
from plm_p1.core import digest
from plm_p1.__main__ import write_json

ROOT=Path(__file__).resolve().parent


def main():
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser()
    parser.add_argument("--split",choices=["development","evaluation"],default="development")
    parser.add_argument("--out-dir",default=str(ROOT/"results"))
    parser.add_argument("--record-first",action="store_true")
    args=parser.parse_args()
    out=Path(args.out_dir).resolve()
    if args.split=="evaluation":
        from freeze_release import verify
        if not verify()["valid"]: raise SystemExit("Frozen sources required before evaluation")
        if args.record_first:
            if (ROOT/"FIRST_EVALUATION.json").exists(): raise SystemExit("First evaluation already recorded")
            with (ROOT/"EVALUATION_STARTED.json").open("x",encoding="utf-8") as f:
                json.dump({"started_at_utc":datetime.now(timezone.utc).isoformat(),"protocol_hash":digest(protocol()),"source_manifest_hash":digest(json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8")))},f,indent=2)
                f.write("\n")
        elif not (ROOT/"FIRST_EVALUATION.json").exists(): raise SystemExit("Use --record-first for first evaluation")
        elif out==ROOT/"results": raise SystemExit("Replay must use a separate --out-dir")
    elif args.record_first: raise SystemExit("record-first applies to evaluation only")
    out.mkdir(parents=True,exist_ok=True)
    result=run_suite(args.split,workers=protocol()["workers"])
    path=out/(args.split.upper()+"_RESULTS.json")
    if args.split=="development" and path.exists(): raise SystemExit("Use another output directory; preserve prior development results")
    write_json(path,result)
    (out/(args.split.upper()+"_REPORT.md")).write_text(render_report(result),encoding="utf-8")
    if args.record_first:
        with (ROOT/"FIRST_EVALUATION.json").open("x",encoding="utf-8") as f:
            json.dump({"result_hash":digest(result),"protocol_hash":result["protocol_hash"],"acceptance":result["acceptance"]},f,indent=2)
            f.write("\n")
    print(json.dumps({"split":args.split,"queries":len(result["rows"]),"acceptance_passed":result["acceptance_passed"],"failed":[k for k,v in result["acceptance"].items() if not v]},indent=2))


if __name__=="__main__": main()
