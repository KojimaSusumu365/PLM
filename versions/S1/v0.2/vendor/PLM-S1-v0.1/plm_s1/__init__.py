"""Synthetic baseband SS prototype. Numerical recovery never authorizes inference."""
import os
from pathlib import Path
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
BASELINE = Path(__file__).resolve().parents[1] / "vendor" / "PLM-P1-v0.2"
for name, module in list(sys.modules.items()):
    if name == "plm_p1_v02" or name.startswith("plm_p1_v02."):
        if not Path(module.__file__).resolve().is_relative_to(BASELINE.resolve()):
            raise RuntimeError("Conflicting P1 v0.2 dependency")
if str(BASELINE) not in sys.path:
    sys.path.append(str(BASELINE))
import plm_p1_v02

VERSION = "PLM-S1 v0.1"
