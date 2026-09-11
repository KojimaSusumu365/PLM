"""Evaluation-only legacy controls and independent language scorer."""
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent
V04 = ROOT / "vendor" / "PLM-L1-v0.4"
V03 = V04 / "vendor" / "PLM-L1-v0.3"
V02 = V03 / "vendor" / "PLM-L1-v0.2"
V01 = V02 / "vendor" / "PLM-L1-v0.1"
for path in (V04, V03, V02, V01):
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


def paired_models(pairs, seed, dimension):
    from plm_l1_v05.training import fit
    from plm_l1_v04.training import fit as old_fit
    new, old = fit(pairs, data("lexicon"), seed=seed, dimension=dimension), old_fit(pairs, data("lexicon"), seed=seed, dimension=dimension)
    equal = True
    for name, memory in new.memories.items():
        before = old.memories[name]
        equal &= len(memory.groups) == len(before.groups)
        for a,b in zip(memory.groups,before.groups):
            equal &= a[0] == b[0] and a[2] == b[2] and bool(np.array_equal(a[1],b[1]))
    if not equal:
        raise ValueError("numerical learning changed")
    return new,old
