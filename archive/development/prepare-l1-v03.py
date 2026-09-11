"""Add a release workspace without editing earlier releases."""
import hashlib
import json
from pathlib import Path
import shutil

BASE = Path(__file__).resolve().parent.parent / "outputs"
ROOT = BASE / "PLM-L1-v0.3"
assert not ROOT.exists()
ROOT.mkdir()
for name in ("plm_l1_v03", "data", "tests", "evaluation", "verification"):
    (ROOT / name).mkdir()
files = []
for name in ("PLM-L1-v0.1", "PLM-L1-v0.2", "PLM-P1-v0.2", "PLM-S1-v0.2"):
    files.extend(p for p in (BASE / name).rglob("*") if p.is_file())
    files.append(BASE / (name + ".zip"))
baseline = {p.relative_to(BASE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
(ROOT / "verification" / "PRESERVED_BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
shutil.copytree(BASE / "PLM-L1-v0.2", ROOT / "vendor" / "PLM-L1-v0.2")
for name in ("train.json", "development.json", "evaluation.json", "lexicon.json"):
    shutil.copyfile(BASE / "PLM-L1-v0.2" / "data" / name, ROOT / "data" / name)
shutil.copyfile(BASE / "PLM-L1-v0.1" / "plm_l1" / "algebra.py", ROOT / "plm_l1_v03" / "algebra.py")
print(json.dumps({"preserved_files": len(baseline), "vendor_files": len(list((ROOT / "vendor").rglob("*")))}))
