import os
os.environ.setdefault("OPENBLAS_NUM_THREADS","1")
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from freeze_release import verify
from plm_p1_v02.evaluation import run_suite,render_report,protocol
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
    if args.split=="evaluation":
        if not verify()["valid"]: raise SystemExit("Frozen sources required")
        if args.record_first:
            if (ROOT/"FIRST_EVALUATION.json").exists(): raise SystemExit("First evaluation already recorded")
            with (ROOT/"EVALUATION_STARTED.json").open("x",encoding="utf-8") as f:
                json.dump({"started_at_utc":datetime.now(timezone.utc).isoformat(),"protocol_hash":digest(protocol()),"source_manifest_hash":digest(json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8")))},f,indent=2)
                f.write("\n")
        elif not (ROOT/"FIRST_EVALUATION.json").exists():
            raise SystemExit("Use --record-first for first evaluation; do not bypass first-run evidence")
    elif args.record_first:
        raise SystemExit("record-first applies to evaluation only")
    result=run_suite(args.split)
    out=Path(args.out_dir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    path=out/(args.split.upper()+"_RESULTS.json")
    # Never overwrite the canonical first evaluation files.
    if args.split=="evaluation" and not args.record_first and path==ROOT/"results/EVALUATION_RESULTS.json":
        raise SystemExit("Replay must use a separate --out-dir")
    write_json(path,result)
    (out/(args.split.upper()+"_REPORT.md")).write_text(render_report(result),encoding="utf-8")
    if args.record_first:
        with (ROOT/"FIRST_EVALUATION.json").open("x",encoding="utf-8") as f:
            json.dump({"result_hash":digest(result),"protocol_hash":result["protocol_hash"],"acceptance":result["acceptance"]},f,indent=2)
            f.write("\n")
    print(json.dumps({"split":args.split,"comparison_queries":len(result["rows"]),"acceptance":result["acceptance"]},indent=2))


if __name__=="__main__": main()
