"""Record actual equal reruns and prepack verification without editing source."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / "outputs" / "PLM-L1-v0.4"
sys.path.insert(0, str(ROOT))
from evaluate import verify_freeze
from plm_l1_v04.runtime import Model

repeat = WORK / "plm-l1-v04-evaluation-repeat"
first = ROOT / "results"
verification = WORK / "plm-l1-v04-prepack-verification"
equal = {}
for relative in ("EVALUATION.json", "EVALUATION_REPORT.md", "model/model.json"):
    equal[relative] = (first / relative).read_bytes() == (repeat / relative).read_bytes()
assert all(equal.values())
with np.load(first / "model" / "weights.npz", allow_pickle=False) as a, np.load(repeat / "model" / "weights.npz", allow_pickle=False) as b:
    assert a.files == b.files
    weight_equal = {name: bool(np.array_equal(a[name], b[name])) for name in a.files}
    raw_weight_bytes = sum(a[name].nbytes for name in a.files)
assert all(weight_equal.values())
tests = json.loads((verification / "VERIFICATION.json").read_text(encoding="utf-8"))
assert tests["status"] == "passed" and not tests["preflight"]
assert sum(tests["test_counts"].values()) == 198 and tests["acceptance_checks"] == 209
result = json.loads((first / "EVALUATION.json").read_text(encoding="utf-8"))
assert result["passed"] and len(result["results"]) == 64 and len(result["references"]) == 8 and len(result["stress"]) == 6
baseline = json.loads((ROOT / "verification" / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
assert len(baseline) == 948
assert all(hashlib.sha256((ROOT.parent / name).read_bytes()).hexdigest() == sha for name, sha in baseline.items())
record = {"status": "passed", "source_freeze": verify_freeze(), "result_digest": result["result_digest"],
          "complete_numeric_runs": 2, "equal_file_bytes": equal, "equal_weight_arrays": weight_equal,
          "weight_comparison_note": "NPZ arrays compared, not ZIP-container timestamps.",
          "primary_model_fingerprint": Model.load(first / "model").fingerprint,
          "phase_vector_count": len(weight_equal), "raw_phase_weights_bytes": raw_weight_bytes,
          "test_counts": tests["test_counts"], "acceptance_checks": len(result["checks"]),
          "preserved_previous_release_files": len(baseline), "numeric_rows": len(result["results"]),
          "table_reference_rows": len(result["references"]), "stress_rows": len(result["stress"]),
          "python": sys.version, "numpy": np.__version__}
with (ROOT / "verification" / "REPRODUCIBILITY.json").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
for source in [verification / "VERIFICATION.json", *sorted(verification.glob("*.log"))]:
    target = ROOT / "verification" / source.name
    assert not target.exists()
    shutil.copyfile(source, target)
print(json.dumps(record, ensure_ascii=False, indent=2))
