"""Use byte-preserved v0.1 phase primitives and a fixed generation model."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "PLM-L1-v0.1"
if str(VENDOR) not in sys.path:
    # Keep the calling release's scripts ahead of similarly named v0.1 scripts.
    sys.path.insert(1, str(VENDOR))
from plm_l1.algebra import Book, Memory, learn, canonical, digest, require
from plm_l1.runtime import Model as LegacyModel


def generator():
    return LegacyModel.load(VENDOR / "results" / "model")
