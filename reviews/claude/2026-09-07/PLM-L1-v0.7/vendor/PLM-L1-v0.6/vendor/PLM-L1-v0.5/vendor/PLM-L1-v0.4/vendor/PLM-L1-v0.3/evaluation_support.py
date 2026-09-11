"""Evaluator-only language oracle and ordinary lookup reference."""
import copy
import json
from collections import Counter
from pathlib import Path
from plm_l1_v03.algebra import canonical
from plm_l1_v03.features import aligned_examples, Space, END, CONTENT
from plm_l1_v03.bridge import fixed_reader

ROOT = Path(__file__).resolve().parent


def data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


def oracle():
    # Only the evaluator loads this old independent bounded grammar.
    fixed_reader()
    from plm_l1.oracle import interpret, INVALID, PATTERNS
    return interpret, INVALID, PATTERNS


def alter_meaning(meaning, condition):
    m = dict(meaning)
    if condition == "roles_swapped":
        m["subject"], m["object"] = m["object"], m["subject"]
    if condition == "states_flipped":
        m["polarity"] = "polarity:negative" if m["polarity"] == "polarity:positive" else "polarity:positive"
        m["modality"] = "modality:asserted" if m["modality"] == "modality:hypothetical" else "modality:hypothetical"
    return m


def marker_map():
    return {s: f"~M{i}~" for i, s in enumerate(sorted(t["surface"] for t in data("lexicon")["tokens"] if t["kind"] == "marker"))}


def rename(text, mapping):
    for a in sorted(mapping, key=lambda s: (-len(s), s)):
        text = text.replace(a, mapping[a])
    return text


def transform(pairs, lexicon, condition):
    pairs, lexicon = copy.deepcopy(pairs), copy.deepcopy(lexicon)
    for row in pairs:
        row["meaning"] = alter_meaning(row["meaning"], condition)
        if condition == "markers_renamed":
            row["text"] = rename(row["text"], marker_map())
    if condition == "markers_renamed":
        mapping = marker_map()
        for token in lexicon["tokens"]:
            if token["kind"] == "marker":
                token["surface"] = mapping[token["surface"]]
    return pairs, lexicon


def score(text, meaning, goal, condition, interpretor, patterns):
    if condition == "markers_renamed" and type(text) is str:
        text = rename(text, {v: k for k, v in marker_map().items()})
    found = interpretor(text)
    if found is None:
        return {"meaning_exact": False, "goal_exact": False, "wrong_slots": list(meaning)}
    found = alter_meaning(found, condition)
    first = next(("subject" if i == 0 else "object" for i, p in enumerate(patterns) if p.fullmatch(text)), None)
    if condition == "roles_swapped":
        first = "object" if first == "subject" else "subject"
    return {"meaning_exact": found == meaning, "goal_exact": first == goal,
            "wrong_slots": [r for r in meaning if meaning[r] != found[r]]}


class LookupWriter:
    """Same pair-derived prefix targets, ordinary maps, no phase codec needed."""
    def __init__(self, pairs, lexicon):
        examples = aligned_examples(pairs, lexicon)
        self.space = Space(None)
        self.tables = {}
        for row in examples:
            for i, symbol in enumerate(row["sequence"] + [END]):
                key = canonical(self.space.context(row["meaning"], row["goal"], row["sequence"][:i]))
                self.tables.setdefault(key, Counter())[symbol] += 1
        self.lexical = {t["value"]: t["surface"] for t in lexicon["tokens"] if t["value"] is not None}

    def generate(self, meaning, goal):
        prefix, output, used = [], [], set()
        for _ in range(12):
            key = canonical(self.space.context(meaning, goal, prefix))
            candidates = self.tables.get(key)
            if not candidates or len(candidates) != 1:
                return None
            symbol = next(iter(candidates))
            if symbol == END:
                return "".join(output) if used == set(CONTENT) else None
            kind, value = json.loads(symbol)
            if kind == "slot":
                if value in used or (not used and value != goal):
                    return None
                used.add(value)
                output.append(self.lexical[meaning[value]])
            else:
                output.append(value)
            prefix.append(symbol)
        return None
