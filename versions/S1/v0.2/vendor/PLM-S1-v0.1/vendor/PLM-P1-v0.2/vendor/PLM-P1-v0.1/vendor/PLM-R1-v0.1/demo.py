"""Generate internal demonstration artifacts, NOT independent semantic evaluation."""
import argparse
import json
from pathlib import Path
import tempfile
from plm_r1 import ObservationStore, analyze
from plm_r1.contract import load_json
from plm_r1.evaluation import prepare, evaluate, task_manifest
from plm_r1.store import markdown

ROOT = Path(__file__).resolve().parent


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(ROOT / "examples"))
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases = load_json(ROOT / "evaluation" / "integration_cases.json")
    receipts = []
    # Keep demo reviews out of real databases; exports retain explicitly internal provenance.
    with tempfile.TemporaryDirectory(prefix="plm-r1-demo-") as temp:
        with ObservationStore(str(Path(temp) / "demo.sqlite3")) as store:
            for case in cases:
                result = analyze(case["inputs"])
                receipt = store.ingest_analysis(result, source_id="internal:" + case["case_id"])
                receipts.append(dict(case_id=case["case_id"], **receipt))
                if case.get("known_issue"):
                    store.review(event_id="known-gap:" + case["case_id"], document_id=result["document_id"],
                                 target_id=result["document_id"], reviewer_id="internal_implementation_note_not_independent_reviewer",
                                 decision="needs_review", **case["known_issue"])
            duplicate = store.ingest_analysis(analyze(cases[0]["inputs"]), source_id="internal:active")
            alias = store.ingest_analysis(analyze(cases[0]["inputs"]), source_id="internal:active-copy")
            ledger = store.ledger()
            write(out / "REVIEW_LEDGER.json", ledger)
            (out / "REVIEW_LEDGER.md").write_text(markdown(ledger), encoding="utf-8")
    write(out / "DEMO_RECEIPTS.json", {"dataset_kind": "internal_synthetic_regressions_not_independent",
                                      "receipts": receipts, "repeat_import": duplicate, "same_content_other_source": alias})
    blank = prepare([])
    write(ROOT / "evaluation" / "PILOT_ANNOTATIONS_TEMPLATE.json", blank)
    write(ROOT / "evaluation" / "PILOT_TASK_MANIFEST_TEMPLATE.json", task_manifest(blank))
    write(ROOT / "evaluation" / "INDEPENDENT_EVALUATION_STATUS.json", evaluate(blank))
    write(out / "INPUTS.json", cases[0]["inputs"])
    summary = {k: ledger[k] for k in ("unique_content_count", "source_revision_count", "observation_count", "inference_enabled")}
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
