"""Bounded synthetic SS acquisition; numerical recovery never enables inference."""
import os
from pathlib import Path
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
BASELINE = Path(__file__).resolve().parents[1] / "vendor/PLM-S1-v0.1"
for name, module in list(sys.modules.items()):
    if name == "plm_s1" or name.startswith("plm_s1."):
        if not Path(module.__file__).resolve().is_relative_to(BASELINE.resolve()):
            raise RuntimeError("Conflicting S1 v0.1 dependency")
if str(BASELINE) not in sys.path:
    sys.path.append(str(BASELINE))
import plm_s1

VERSION = "PLM-S1 v0.2"
