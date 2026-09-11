"""Only emit reproducibility/preservation claims after checking actual files."""
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / "outputs" / "PLM-L1-v0.3"
REPEAT = WORK / "plm-l1-v03-evaluation-repeat"
PREPACK = WORK / "plm-l1-v03-prepack-verification"
VERIFY = ROOT / "verification"

first = ROOT / "results" / "EVALUATION.json"
assert first.read_bytes() == (REPEAT / "EVALUATION.json").read_bytes(), "full numerical results differ"
assert (ROOT / "results" / "EVALUATION_REPORT.md").read_bytes() == (REPEAT / "EVALUATION_REPORT.md").read_bytes()
result = json.loads(first.read_text(encoding="utf-8"))
assert result["passed"] and len(result["checks"]) == 113 and all(c["passed"] for c in result["checks"])
writer = ROOT / "results" / "writer"
assert (writer / "writer.json").read_bytes() == (REPEAT / "writer" / "writer.json").read_bytes()
with np.load(writer / "weights.npz", allow_pickle=False) as a, np.load(REPEAT / "writer" / "weights.npz", allow_pickle=False) as b:
    assert set(a.files) == set(b.files)
    assert all(np.array_equal(a[name], b[name]) for name in a.files)
    weight_bytes = sum(a[name].nbytes for name in a.files)
    memories = len(a.files)
prepack = json.loads((PREPACK / "VERIFICATION.json").read_text(encoding="utf-8"))
assert prepack["status"] == "passed" and prepack["result_digest"] == result["result_digest"]
assert prepack["test_counts"] == {"NEW_TESTS": 53, "V02_TESTS": 52, "V01_TESTS": 47}
baseline = json.loads((VERIFY / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
assert all(hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() == expected for name, expected in baseline.items())
record = {"status": "passed", "full_numeric_evaluation_runs": 2, "full_result_json_bytes_equal": True,
          "report_bytes_equal": True, "writer_metadata_bytes_equal": True, "writer_weight_arrays_exact_equal": True,
          "result_digest": result["result_digest"], "source_freeze": result["freeze_hash"],
          "result_file_sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
          "conditions": 8, "evaluation_code_seeds": 8, "standalone_requests_per_seed_condition": 192,
          "roundtrip_requests_per_seed_condition": 384, "stress_runs": len(result["stress"]), "reference_runs": len(result["references"]),
          "acceptance_checks": 113, "numerical_writer_memories": memories, "raw_writer_weight_bytes": weight_bytes,
          "preserved_old_files": len(baseline), "note": "All per-example outcomes, stress and references compared. Independent runs use the same reused corpus, not independent corpora. Weight size excludes fixed reader, metadata, candidate bases, caches and process memory."}
with (VERIFY / "REPRODUCIBILITY.json").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
for source in sorted(PREPACK.glob("*.log")) + [PREPACK / "VERIFICATION.json"]:
    target = VERIFY / ("PREPACK_VERIFICATION.json" if source.suffix == ".json" else source.name)
    assert not target.exists()
    shutil.copyfile(source, target)
print(json.dumps(record, ensure_ascii=False, indent=2))
