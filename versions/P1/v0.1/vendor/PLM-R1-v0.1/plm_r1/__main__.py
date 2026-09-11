"""CLI. All JSON outputs are explicit local artifacts; no network or inference."""
import argparse
import json
from pathlib import Path
from .contract import load_json
from .evaluation import prepare, evaluate, task_manifest
from .producer import analyze, verify_dependency
from .store import ObservationStore, markdown


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="PLM-R1 v0.1 observation-only consumer")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--db", required=True)
    ingest.add_argument("--input", required=True, help="JSON: raw inputs, full analysis, or C2 observation envelope")
    ingest.add_argument("--kind", choices=["inputs", "analysis", "envelope"], required=True)
    ingest.add_argument("--source-id", required=True)
    ingest.add_argument("--revision", default="1")
    ledger = sub.add_parser("ledger")
    ledger.add_argument("--db", required=True)
    ledger.add_argument("--json-out", required=True)
    ledger.add_argument("--markdown-out", required=True)
    review = sub.add_parser("review")
    review.add_argument("--db", required=True)
    review.add_argument("--input", required=True, help="JSON keyword arguments for ObservationStore.review")
    prep = sub.add_parser("prepare-evaluation")
    prep.add_argument("--corpus", required=True)
    prep.add_argument("--out", required=True)
    prep.add_argument("--manifest-out", required=True, help="Keep this task-content freeze separate from editable annotations")
    prep.add_argument("--dataset-kind", choices=["real_world", "synthetic"], default="real_world")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--annotations", required=True)
    ev.add_argument("--out", required=True)
    ev.add_argument("--task-manifest")
    sub.add_parser("verify-dependency")
    args = parser.parse_args()
    try:
        if args.command == "verify-dependency":
            result = verify_dependency()
        elif args.command == "prepare-evaluation":
            result = prepare(load_json(args.corpus), dataset_kind=args.dataset_kind)
            write_json(args.out, result)
            write_json(args.manifest_out, task_manifest(result))
            result = {"tasks_prepared": len(result["items"]), "gold_prefilled": False}
        elif args.command == "evaluate":
            result = evaluate(load_json(args.annotations), load_json(args.task_manifest) if args.task_manifest else None)
            write_json(args.out, result)
        else:
            with ObservationStore(args.db) as store:
                if args.command == "ingest":
                    value = load_json(args.input)
                    if args.kind == "inputs":
                        value = analyze(value)
                    method = store.ingest if args.kind == "envelope" else store.ingest_analysis
                    result = method(value, source_id=args.source_id, revision=args.revision)
                elif args.command == "review":
                    result = store.review(**load_json(args.input))
                else:
                    result = store.ledger()
                    write_json(args.json_out, result)
                    Path(args.markdown_out).write_text(markdown(result), encoding="utf-8")
                    result = {k: v for k, v in result.items() if k != "documents"}
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, "Rejected: " + str(error) + "\n")


if __name__ == "__main__":
    main()
