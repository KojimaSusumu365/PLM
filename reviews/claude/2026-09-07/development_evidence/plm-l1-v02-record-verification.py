"""Record checks only after first and repeat results have been compared."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / "outputs" / "PLM-L1-v0.2"
REPEAT = WORK / "plm-l1-v02-evaluation-repeat"
PREPACK = WORK / "plm-l1-v02-prepack-verification"
VERIFY = ROOT / "verification"

first = ROOT / "results" / "EVALUATION.json"
repeat = REPEAT / "EVALUATION.json"
assert first.read_bytes() == repeat.read_bytes(), "full evaluation JSON differs"
assert (ROOT / "results" / "EVALUATION_REPORT.md").read_bytes() == (REPEAT / "EVALUATION_REPORT.md").read_bytes()
result = json.loads(first.read_text(encoding="utf-8"))
assert result["passed"] and len(result["checks"]) == 97 and all(c["passed"] for c in result["checks"])
reader = ROOT / "results" / "reader"
assert (reader / "reader.json").read_bytes() == (REPEAT / "reader" / "reader.json").read_bytes()
with np.load(reader / "weights.npz", allow_pickle=False) as a, np.load(REPEAT / "reader" / "weights.npz", allow_pickle=False) as b:
    assert set(a.files) == set(b.files)
    assert all(np.array_equal(a[name], b[name]) for name in a.files)
    raw_weight_bytes = sum(a[name].nbytes for name in a.files)
    numerical_memories = len(a.files)
prepack = json.loads((PREPACK / "VERIFICATION.json").read_text(encoding="utf-8"))
assert prepack["status"] == "passed" and prepack["result_digest"] == result["result_digest"]
assert prepack["test_counts"] == {"new": 52, "v01": 47}
record = {
    "status": "passed",
    "full_evaluation_runs": 2,
    "full_result_json_bytes_equal": True,
    "report_bytes_equal": True,
    "reader_metadata_bytes_equal": True,
    "reader_weight_arrays_exact_equal": True,
    "first_result_file_sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
    "result_digest": result["result_digest"],
    "source_freeze": result["freeze_hash"],
    "conditions": 7,
    "evaluation_code_seeds": 8,
    "evaluation_sentences_per_condition_seed": 192,
    "stress_runs": len(result["stress"]),
    "reference_runs": len(result["references"]),
    "acceptance_checks": len(result["checks"]),
    "numerical_memories": numerical_memories,
    "raw_reader_weight_bytes_excluding_metadata_cache_generator": raw_weight_bytes,
    "note": "All per-example outcomes, stress and reference results compared, not only aggregate success counts. Repeated code seeds/corpus runs are not new independent corpora.",
}
with (VERIFY / "REPRODUCIBILITY.json").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
for source in sorted(PREPACK.glob("*.log")) + [PREPACK / "VERIFICATION.json"]:
    target = VERIFY / ("PREPACK_VERIFICATION.json" if source.suffix == ".json" else source.name)
    assert not target.exists()
    shutil.copyfile(source, target)
print(json.dumps(record, ensure_ascii=False, indent=2))
