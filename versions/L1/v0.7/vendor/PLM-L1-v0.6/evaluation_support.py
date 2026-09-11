"""Evaluation-only legacy controls and independent language scorer."""
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent
V05 = ROOT / "vendor" / "PLM-L1-v0.5"
V04 = V05 / "vendor" / "PLM-L1-v0.4"
V03 = V04 / "vendor" / "PLM-L1-v0.3"
V02 = V03 / "vendor" / "PLM-L1-v0.2"
V01 = V02 / "vendor" / "PLM-L1-v0.1"
for path in (V05, V04, V03, V02, V01):
    if str(path) not in sys.path:
        sys.path.append(str(path))
spec = importlib.util.spec_from_file_location("legacy_v04_evaluation_support", V04 / "evaluation_support.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
FOLDS, GOALS = legacy.FOLDS, legacy.GOALS
heldout, text_goal, interpret, INVALID = legacy.heldout, legacy.text_goal, legacy.interpret, legacy.INVALID
OldSS, PartialTable, OldTable = legacy.OldSS, legacy.PartialTable, legacy.OldTable
opaque, normalize_markers = legacy.opaque, legacy.normalize_markers


def data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def train_for(fold):
    return data("folds/" + fold + "/train")
