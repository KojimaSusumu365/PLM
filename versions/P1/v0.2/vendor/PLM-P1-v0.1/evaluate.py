import argparse
import sys
import json
from pathlib import Path
from plm_p1.evaluation import run_suite, render_report
from plm_p1.__main__ import write_json
from plm_p1.core import digest

ROOT = Path(__file__).resolve().parent


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["development", "evaluation"], default="development")
    parser.add_argument("--out-dir", default=str(ROOT / "results"))
    parser.add_argument("--record-first", action="store_true")
    args = parser.parse_args()
    if args.split == "evaluation":
        from freeze_release import verify
        if not verify()["valid"]:
            raise SystemExit("Frozen sources required before evaluation")
    if args.record_first and (args.split != "evaluation" or (ROOT / "FIRST_EVALUATION.json").exists()):
        raise SystemExit("First evaluation can only be recorded once, on evaluation split")
    result = run_suite(args.split)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / (args.split.upper() + "_RESULTS.json"), result)
    (out / (args.split.upper() + "_REPORT.md")).write_text(render_report(result), encoding="utf-8")
    if args.record_first:
        with (ROOT / "FIRST_EVALUATION.json").open("x", encoding="utf-8") as stream:
            json.dump({"result_hash": digest(result), "protocol_hash": result["protocol_hash"],
                       "acceptance": result["acceptance"], "dataset_kind": result["dataset_kind"]}, stream, indent=2)
            stream.write("\n")
    print(render_report(result))


if __name__ == "__main__":
    main()
