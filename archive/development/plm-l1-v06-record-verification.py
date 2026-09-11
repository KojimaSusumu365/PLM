"""Record completed runs and checks without changing frozen source."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np

WORK=Path(__file__).resolve().parent
ROOT=WORK.parent/"outputs"/"PLM-L1-v0.6"
sys.path.insert(0,str(ROOT))
from evaluate import verify_freeze,judge
from plm_l1_v06.runtime import Model

first=ROOT/"results"
repeat=WORK/"plm-l1-v06-evaluation-repeat"
verification=WORK/"plm-l1-v06-prepack-verification"
equal={name:(first/name).read_bytes()==(repeat/name).read_bytes() for name in ("EVALUATION.json","REPORT.md","model/model.json")}
assert all(equal.values())
with np.load(first/"model"/"weights.npz",allow_pickle=False) as a,np.load(repeat/"model"/"weights.npz",allow_pickle=False) as b:
    assert a.files==b.files
    weight_equal={name:bool(np.array_equal(a[name],b[name])) for name in a.files}
    raw_bytes=sum(a[name].nbytes for name in a.files)
assert all(weight_equal.values())
tests=json.loads((verification/"VERIFICATION.json").read_text(encoding="utf-8"))
assert tests["status"]=="passed" and not tests["preflight"]
assert sum(tests["test_counts"].values())==341 and tests["acceptance_checks"]==351
r=json.loads((first/"EVALUATION.json").read_text(encoding="utf-8"))
p=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
assert r["passed"] and judge(r,p)==r["checks"] and len(r["standard"])==16 and len(r["memory"])==34
baseline=json.loads((ROOT/"verification"/"PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
assert len(baseline)==1421
assert all(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()==sha for name,sha in baseline.items())
core_equal={name:(ROOT/"plm_l1_v06"/name).read_bytes()==(ROOT/"vendor"/"PLM-L1-v0.5"/"plm_l1_v05"/name).read_bytes() for name in ("algebra.py","projection.py","features.py","lexicon.py","reader.py")}
assert all(core_equal.values())
model=Model.load(first/"model")
record={"status":"passed","source_freeze":verify_freeze(),"result_digest":r["result_digest"],"complete_numeric_runs":2,
        "equal_file_bytes":equal,"equal_weight_arrays":weight_equal,"unchanged_core_files":core_equal,
        "primary_model_fingerprint":model.fingerprint,"memory_block_count":len(weight_equal),"serialized_block_state_bytes":raw_bytes,
        "primary_memory_storage":{n:m.storage() for n,m in model.memories.items()},
        "test_counts":tests["test_counts"],"acceptance_checks":len(r["checks"]),"preserved_previous_release_files":len(baseline),
        "standard_conditions":len(r["standard"]),"standard_models":sum(len(v["methods"]) for v in r["standard"]),
        "memory_conditions":len(r["memory"]),"memory_models":sum(len(v["methods"]) for v in r["memory"]),
        "numpy":np.__version__,"python":sys.version,"weight_comparison_note":"NPZ uint8 arrays compared exactly, not ZIP-container timestamps. Timing/tracemalloc in TELEMETRY are measured, deliberately excluded from deterministic equality."}
with (ROOT/"verification"/"REPRODUCIBILITY.json").open("x",encoding="utf-8") as stream:
    stream.write(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
for path in [verification/"VERIFICATION.json",*sorted(verification.glob("*.log"))]:
    target=ROOT/"verification"/path.name
    assert not target.exists()
    shutil.copyfile(path,target)
development=WORK/"plm-l1-v06-development"/"EVALUATION.json"
d=json.loads(development.read_text(encoding="utf-8"))
development_record={"scope":"Exploratory pre-freeze run. Final source added additional weight digests and count audits after this run; no thresholds or numerical algorithm were changed.",
                    "sha256":hashlib.sha256(development.read_bytes()).hexdigest(),"result_digest":d["result_digest"],"standard_conditions":len(d["standard"]),"memory_conditions":len(d["memory"])}
with (ROOT/"verification"/"DEVELOPMENT_RECORD.json").open("x",encoding="utf-8") as stream:
    stream.write(json.dumps(development_record,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(record,ensure_ascii=False,indent=2))
