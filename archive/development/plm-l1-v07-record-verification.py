import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np

WORK=Path(__file__).resolve().parent
ROOT=WORK.parent/"outputs"/"PLM-L1-v0.7"
sys.path.insert(0,str(ROOT))
from evaluate import verify_freeze,judge
from plm_l1_v07.runtime import EventModel

first=ROOT/"results"; repeat=WORK/"plm-l1-v07-evaluation-repeat"; verification=WORK/"plm-l1-v07-prepack-verification"
equal={name:(first/name).read_bytes()==(repeat/name).read_bytes() for name in ("EVALUATION.json","REPORT.md","model/model.json","model/component/model.json")}
assert all(equal.values())
with np.load(first/"model"/"component"/"weights.npz",allow_pickle=False) as a,np.load(repeat/"model"/"component"/"weights.npz",allow_pickle=False) as b:
    assert a.files==b.files
    weights={name:bool(np.array_equal(a[name],b[name])) for name in a.files}
assert all(weights.values())
tests=json.loads((verification/"VERIFICATION.json").read_text(encoding="utf-8"))
assert tests["status"]=="passed" and not tests["preflight"] and sum(tests["test_counts"].values())==381 and tests["acceptance_checks"]==364
r=json.loads((first/"EVALUATION.json").read_text(encoding="utf-8")); p=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
assert r["passed"] and judge(r,p)==r["checks"]
baseline=json.loads((ROOT/"verification"/"PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
assert len(baseline)==1759 and all(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()==sha for name,sha in baseline.items())
old=ROOT/"vendor"/"PLM-L1-v0.6"/"plm_l1_v06"
component_equal={path.name:path.read_bytes()==(old/path.name).read_bytes() for path in (ROOT/"plm_l1_v06").glob("*.py")}
assert all(component_equal.values())
model=EventModel.load(first/"model")
record={"status":"passed","source_freeze":verify_freeze(),"source_files":len(json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))["files"]),
        "result_digest":r["result_digest"],"complete_numeric_runs":2,"equal_file_bytes":equal,"equal_component_weight_arrays":weights,
        "unchanged_component_code":component_equal,"primary_model_fingerprint":model.fingerprint,"component_fingerprint":model.component.fingerprint,
        "test_counts":tests["test_counts"],"acceptance_checks":len(r["checks"]),"preserved_previous_release_files":len(baseline),
        "standard_conditions":len(r["standard"]),"codec_conditions":len(r["codec"]),"noise_conditions":len(r["noise"]),
        "numpy":np.__version__,"python":sys.version,"note":"NPZ arrays compared exactly, not ZIP-container timestamps; fixed event basis reconstructed from seed. No two-event examples supplied to fitting."}
with (ROOT/"verification"/"REPRODUCIBILITY.json").open("x",encoding="utf-8") as stream:
    stream.write(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
for path in [verification/"VERIFICATION.json",*sorted(verification.glob("*.log"))]:
    target=ROOT/"verification"/path.name
    assert not target.exists(); shutil.copyfile(path,target)
print(json.dumps(record,ensure_ascii=False,indent=2))
