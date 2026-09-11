"""Evaluator-only controls and non-SS lookup reference; not imported by learner."""
import copy
import json
from collections import Counter
from plm_l1_v02.compat import ROOT, canonical
from plm_l1_v02.features import tokenize, abstract, descriptor
from plm_l1_v02.training import observations
from plm_l1.oracle import interpret, INVALID

GOALS = ("subject_first", "object_first")


def load_data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def marker_map(lexicon):
    markers = sorted(t["surface"] for t in lexicon["tokens"] if t["kind"] == "marker")
    return {surface: f"~M{i}~" for i, surface in enumerate(markers)}


def rename_text(text, mapping):
    for surface in sorted(mapping, key=lambda x: (-len(x), x)):
        text = text.replace(surface, mapping[surface])
    return text


def transform(pairs, lexicon, condition):
    rows, vocab = copy.deepcopy(pairs), copy.deepcopy(lexicon)
    if condition == "roles_swapped":
        for row in rows:
            m = row["meaning"]
            m["subject"], m["object"] = m["object"], m["subject"]
    elif condition == "states_flipped":
        for row in rows:
            m = row["meaning"]
            m["polarity"] = "polarity:negative" if m["polarity"] == "polarity:positive" else "polarity:positive"
            m["modality"] = "modality:asserted" if m["modality"] == "modality:hypothetical" else "modality:hypothetical"
    elif condition == "markers_renamed":
        mapping = marker_map(lexicon)
        for row in rows:
            row["text"] = rename_text(row["text"], mapping)
        for token in vocab["tokens"]:
            if token["kind"] == "marker":
                token["surface"] = mapping[token["surface"]]
    return rows, vocab


class LookupReader:
    """Same automatically derived correspondences, ordinary table representation.

    This is a control, not a fallback used by the SS reader. Equal supervision,
    not equal byte footprint or a speed/energy benchmark.
    """
    def __init__(self, pairs, lexicon):
        rows = observations(pairs, lexicon)
        self.tables = {}
        for name, values in rows.items():
            groups = {}
            for key, target in values:
                groups.setdefault(canonical(key), Counter())[target] += 1
            self.tables[name] = {}
            for key, counts in groups.items():
                best = counts.most_common(1)[0]
                self.tables[name][key] = best[0] if best[1] / counts.total() >= .65 else None
        self.kinds = {t["surface"]: t["kind"] for t in lexicon["tokens"]}
        self.values = {t["surface"]: t["value"] for t in lexicon["tokens"]}

    def read(self, text):
        try:
            tokens = tokenize(text, self.kinds)
        except ValueError:
            return None
        shape = abstract(tokens, self.kinds)
        if self.tables["support"].get(canonical(descriptor(shape))) != "supported":
            return None
        slots = {}
        for position, token in enumerate(tokens):
            kind = self.kinds[token]
            if kind == "marker":
                continue
            role = self.tables["roles"].get(canonical(descriptor(shape, position=position, kind=kind)))
            if role not in ("subject", "object", "predicate") or role in slots:
                return None
            slots[role] = self.values[token]
        for slot in ("polarity", "modality"):
            value = self.tables["states"].get(canonical(descriptor(shape, slot=slot)))
            if value is None:
                return None
            slots[slot] = value
        return slots if len(slots) == 5 else None
