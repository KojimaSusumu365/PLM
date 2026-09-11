"""Language-neutral token abstraction and ordered phasor composition.

Known lexical kinds are prior knowledge. No particle, suffix, polarity or
grammar-state meanings occur here. Whole abstract shapes are learned, not
unbounded syntax induction.
"""
import numpy as np
from .compat import canonical, require


def validate_lexicon(lexicon):
    require(type(lexicon) is dict and set(lexicon) == {"tokens", "slot_candidates"}, "invalid lexicon fields")
    require(set(lexicon["slot_candidates"]) == {"subject", "object", "predicate", "polarity", "modality"}, "invalid roles")
    seen = set()
    for token in lexicon["tokens"]:
        require(type(token) is dict and set(token) == {"surface", "kind", "value"}, "invalid lexical fields")
        require(type(token["surface"]) is str and 0 < len(token["surface"]) <= 32 and token["surface"] not in seen, "invalid/duplicate surface")
        require(token["kind"] in ("entity", "predicate", "marker"), "unsupported lexical kind")
        if token["kind"] == "marker":
            require(token["value"] is None, "markers must not carry semantic supervision")
        else:
            require(type(token["value"]) is str and token["value"].startswith(token["kind"] + ":"), "invalid lexical value")
        seen.add(token["surface"])
    for role, candidates in lexicon["slot_candidates"].items():
        require(type(candidates) is list and len(candidates) >= 2 and len(set(candidates)) == len(candidates), "invalid candidate inventory")
        require(all(type(x) is str and x for x in candidates), "invalid candidates")


def tokenize(text, kinds):
    require(type(text) is str and 0 < len(text) <= 256, "empty_or_oversized_input")
    vocabulary = sorted(kinds, key=lambda s: (-len(s), s))
    tokens, offset = [], 0
    while offset < len(text):
        surface = next((s for s in vocabulary if text.startswith(s, offset)), None)
        require(surface is not None, "unknown_token")
        tokens.append(surface)
        require(len(tokens) <= 9, "token_capacity_exceeded")
        offset += len(surface)
    return tokens


def abstract(tokens, kinds):
    return [["kind", kinds[t]] if kinds[t] != "marker" else ["surface", t] for t in tokens]


def descriptor(shape, *, position=None, kind=None, slot=None, ordered=True):
    # Ablation merges exact key identities as well as removing permutations.
    shape = shape if ordered else sorted(shape, key=canonical)
    result = {"shape": shape}
    if position is not None:
        result["position"] = position if ordered else 0
        result["kind"] = kind
    if slot is not None:
        result["slot"] = slot
    return result


class Space:
    def __init__(self, book, ordered=True):
        self.book, self.ordered = book, ordered
        self.cache = {}

    def key(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            shape_key = canonical(description["shape"])
            cache_key = "shape:" + shape_key
            if cache_key not in self.cache:
                value = np.ones(self.book.dimension, dtype=np.complex128)
                for position, token in enumerate(description["shape"]):
                    value *= np.roll(self.book.code("abstract_token", token), 17 * position if self.ordered else 0)
                self.cache[cache_key] = value
            value = self.cache[cache_key].copy()
            for field in ("position", "kind", "slot"):
                if field in description:
                    value *= self.book.code("query_" + field, description[field])
            self.cache[identity] = value
        return self.cache[identity]
