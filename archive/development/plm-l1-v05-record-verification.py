"""Record finished reproducibility and verification; never edit frozen source."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np

WORK=Path(__file__).resolve().parent
ROOT=WORK.parent/"outputs"/"PLM-L1-v0.5"
sys.path.insert(0,str(ROOT))
from evaluate import verify_freeze
from plm_l1_v05.runtime import Model

first=ROOT/"results"
repeat=WORK/"plm-l1-v05-evaluation-repeat"
verification=WORK/"plm-l1-v05-prepack-verification"
equal={name:(first/name).read_bytes()==(repeat/name).read_bytes() for name in ("EVALUATION.json","EVALUATION_REPORT.md","model/model.json")}
assert all(equal.values())
with np.load(first/"model"/"weights.npz",allow_pickle=False) as a,np.load(repeat/"model"/"weights.npz",allow_pickle=False) as b:
    assert a.files==b.files
    weight_equal={name:bool(np.array_equal(a[name],b[name])) for name in a.files}
    raw_bytes=sum(a[name].nbytes for name in a.files)
assert all(weight_equal.values())
tests=json.loads((verification/"VERIFICATION.json").read_text(encoding="utf-8"))
assert tests["status"]=="passed" and not tests["preflight"]
assert sum(tests["test_counts"].values())==268 and tests["acceptance_checks"]==283
r=json.loads((first/"EVALUATION.json").read_text(encoding="utf-8"))
assert r["passed"] and len(r["standard"])==16 and len(r["dimension"])==16 and len(r["channel"])==60 and len(r["memory"])==32
baseline=json.loads((ROOT/"verification"/"PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
assert len(baseline)==1152
assert all(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()==sha for name,sha in baseline.items())
core_equal={name:(ROOT/"plm_l1_v05"/name).read_bytes()==(ROOT/"vendor"/"PLM-L1-v0.4"/"plm_l1_v04"/name).read_bytes() for name in ("algebra.py","projection.py","features.py","lexicon.py")}
assert all(core_equal.values())
record={"status":"passed","source_freeze":verify_freeze(),"result_digest":r["result_digest"],"complete_numeric_runs":2,
        "equal_file_bytes":equal,"equal_weight_arrays":weight_equal,"unchanged_core_files":core_equal,
        "primary_model_fingerprint":Model.load(first/"model").fingerprint,"phase_vector_count":len(weight_equal),"raw_phase_weights_bytes":raw_bytes,
        "test_counts":tests["test_counts"],"acceptance_checks":len(r["checks"]),"preserved_previous_release_files":len(baseline),
        "standard_paired_conditions":len(r["standard"]),"dimension_paired_conditions":len(r["dimension"]),"channel_conditions":len(r["channel"]),"memory_conditions":len(r["memory"]),
        "numpy":np.__version__,"python":sys.version,"weight_comparison_note":"NPZ arrays compared exactly, not ZIP-container timestamps."}
with (ROOT/"verification"/"REPRODUCIBILITY.json").open("x",encoding="utf-8") as stream:
    stream.write(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
for p in [verification/"VERIFICATION.json",*sorted(verification.glob("*.log"))]:
    target=ROOT/"verification"/p.name
    assert not target.exists()
    shutil.copyfile(p,target)
print(json.dumps(record,ensure_ascii=False,indent=2))
