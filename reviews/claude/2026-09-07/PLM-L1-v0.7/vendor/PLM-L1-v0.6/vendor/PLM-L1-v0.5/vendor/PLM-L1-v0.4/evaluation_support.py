"""Evaluator-only splits, independent language scoring, and matched baselines."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from plm_l1_v04.algebra import canonical, digest
from plm_l1_v04.lexicon import aligned_examples, GOALS
from plm_l1_v04.features import observations
from plm_l1_v04.projection import dependency_leaves
from plm_l1_v04.runtime import Model

ROOT = Path(__file__).resolve().parent
V03 = ROOT / "vendor" / "PLM-L1-v0.3"
V02 = V03 / "vendor" / "PLM-L1-v0.2"
for path in (V03, V02, V02 / "vendor" / "PLM-L1-v0.1"):
    if str(path) not in sys.path:
        # unittest may place tests/ at index 0; append legacy packages so their
        # same-named evaluator scripts cannot shadow this release's scripts.
        sys.path.append(str(path))
from plm_l1.oracle import interpret, INVALID, PATTERNS

FOLDS = ("object_negative", "subject_negative", "object_positive", "subject_positive")


def data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def text_goal(text):
    return next(("subject" if i == 0 else "object" for i, p in enumerate(PATTERNS) if p.fullmatch(text)), None)


def heldout(meaning, goal, fold):
    order, polarity = fold.split("_")
    return goal == order and meaning["polarity"] == "polarity:" + polarity


def train_for(fold):
    return data("folds/" + fold + "/train")


def normalize_markers(text, mapping):
    for a in sorted(mapping, key=lambda x: (-len(x), x)):
        text = text.replace(a, mapping[a])
    return text


def opaque(pairs, lexicon):
    pairs, lexicon = copy.deepcopy(pairs), copy.deepcopy(lexicon)
    mapping = {s: f"~M{i}~" for i,s in enumerate(sorted(t["surface"] for t in lexicon["tokens"] if t["kind"] == "marker"))}
    for row in pairs:
        row["text"] = normalize_markers(row["text"], mapping)
    for token in lexicon["tokens"]:
        if token["kind"] == "marker":
            token["surface"] = mapping[token["surface"]]
    return pairs, lexicon, mapping


class OldSS:
    """v0.2 reader and v0.3 writer BOTH retrained on the same restricted pairs."""
    def __init__(self, pairs, lexicon, seed, dimension=8192):
        from plm_l1_v02.training import fit as fit_reader
        from plm_l1_v03.training import fit as fit_writer
        self.reader = fit_reader(pairs, lexicon, seed=seed, dimension=dimension)
        self.writer = fit_writer(pairs, lexicon, seed=seed, dimension=dimension)
        self.fingerprint = digest([self.reader.fingerprint, self.writer.fingerprint])
        self.meta = {"pair_count": len(pairs), "statistics": {"reader": self.reader.meta["statistics"], "writer": self.writer.meta["statistics"]}}

    def read(self, text):
        r = self.reader.read(text)
        if r["status"] != "read":
            return r
        meaning = self.reader.recover(r["packet"])
        if meaning["status"] != "recovered":
            return {"status": "abstain", "reason": "old_meaning_recovery_failed"}
        return {"status": "read", "packet": self.writer.encode(meaning["slots"])}

    def encode(self, meaning):
        return self.writer.encode(meaning)

    def recover(self, packet):
        return self.writer.recover(packet)

    def generate(self, packet, goal="object"):
        return self.writer.generate(packet, goal)


class DictMemory:
    def __init__(self, observations):
        self.leaves = dependency_leaves(observations, True)

    def recall(self, context):
        labels = {label for key, label in self.leaves if all(context.get(k) == v for k,v in key.items())}
        return {"value": next(iter(labels)) if len(labels) == 1 else None}


class PartialTable(Model):
    """Same learned projections/components, but ordinary matching, no phase codec."""
    def __init__(self, pairs, lexicon):
        rows = observations(pairs, lexicon)
        self.memories = {name: DictMemory(row) for name, row in rows.items()}
        self.meta = {"kinds": {t["surface"]:t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"], "pair_count": len(pairs), "statistics": {}}
        self.fingerprint = digest(["partial_table", pairs, lexicon])

    def encode(self, meaning):
        return {"meaning": dict(meaning)}

    def recover(self, packet):
        return {"status": "recovered", "meaning": dict(packet["meaning"])}


def helper(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OldTable(PartialTable):
    def __init__(self, pairs, lexicon):
        self.reader = helper(V02 / "evaluation_support.py", "old_reader_tables").LookupReader(pairs, lexicon)
        self.writer = helper(V03 / "evaluation_support.py", "old_writer_tables").LookupWriter(pairs, lexicon)
        self.fingerprint = digest(["whole_context_table", pairs, lexicon])
        self.meta = {"pair_count":len(pairs), "statistics":{}}

    def read(self, text):
        meaning = self.reader.read(text)
        return {"status":"read", "packet":self.encode(meaning)} if meaning is not None else {"status":"abstain", "reason":"unknown_whole_context"}

    def generate(self, packet, goal="object"):
        text = self.writer.generate(packet["meaning"], goal)
        return {"status":"generated" if text is not None else "abstain", "text":text, "reason":None if text is not None else "unknown_prefix"}
