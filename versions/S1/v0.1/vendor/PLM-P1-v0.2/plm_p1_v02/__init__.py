"""Experimental numerical recovery; never an assertion of semantic truth."""
from pathlib import Path
import os
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

BASELINE = Path(__file__).resolve().parents[1] / "vendor" / "PLM-P1-v0.1"
for name, module in list(sys.modules.items()):
    if name == "plm_p1" or name.startswith("plm_p1."):
        if not Path(module.__file__).resolve().is_relative_to(BASELINE.resolve()):
            raise RuntimeError("Conflicting unfrozen P1 v0.1 module")
if str(BASELINE) not in sys.path:
    sys.path.append(str(BASELINE))

from plm_p1.core import PhaseCodebook, symbol, encode, channel

VERSION = "PLM-P1 v0.2"
