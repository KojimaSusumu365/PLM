"""Explicit lexical priors and automatically aligned prefix features.

No language-specific grammar, supplied emission labels or state traces.
The alignment/copy architecture IS a designed inductive bias, not discovered.
"""
import numpy as np
from .algebra import canonical, require

CONTENT = ("subject", "object", "predicate")
ROLES = CONTENT + ("polarity", "modality")
GOALS = ("subject", "object")
END = canonical(["end"])


def validate_meaning(meaning, candidates):
    require(type(meaning) is dict and set(meaning) == set(ROLES), "invalid_meaning_fields")
    require(all(type(meaning[r]) is str and meaning[r] in candidates[r] for r in ROLES), "unknown_meaning_value")


def validate_lexicon(lexicon):
    require(type(lexicon) is dict and set(lexicon) == {"tokens", "slot_candidates"}, "invalid_lexicon_fields")
    candidates = lexicon["slot_candidates"]
    require(type(candidates) is dict and set(candidates) == set(ROLES), "invalid_slot_inventory")
    for values in candidates.values():
        require(type(values) is list and len(values) >= 2 and all(type(v) is str and v for v in values) and len(set(values)) == len(values), "invalid_candidates")
    require(type(lexicon["tokens"]) is list and 0 < len(lexicon["tokens"]) <= 256, "invalid_tokens")
    surfaces, meanings = set(), set()
    for token in lexicon["tokens"]:
        require(type(token) is dict and set(token) == {"surface", "kind", "value"}, "invalid_lexical_fields")
        surface, kind, value = token["surface"], token["kind"], token["value"]
        require(type(surface) is str and 0 < len(surface) <= 32 and surface not in surfaces, "invalid_surface")
        require(kind in ("entity", "predicate", "marker"), "invalid_kind")
        if kind == "marker":
            require(value is None, "marker_semantics_prohibited")
        else:
            require(type(value) is str and value.startswith(kind + ":") and value not in meanings, "ambiguous_lexical_realization")
            require(any(value in candidates[r] for r in CONTENT), "lexical_value_outside_candidates")
            meanings.add(value)
        surfaces.add(surface)


def tokenize(text, vocabulary):
    require(type(text) is str and 0 < len(text) <= 256, "empty_or_oversized_text")
    ordered = sorted(vocabulary, key=lambda s: (-len(s), s))
    offset, tokens = 0, []
    while offset < len(text):
        token = next((t for t in ordered if text.startswith(t, offset)), None)
        require(token is not None, "unknown_token")
        tokens.append(token)
        require(len(tokens) <= 9, "token_capacity_exceeded")
        offset += len(token)
    return tokens


def aligned_examples(pairs, lexicon):
    """Infer abstract emissions from lexical identity and paired semantic slots.

    Prefixes and next-symbol targets are derived internally from these pairs.
    This is supervised sequence learning, not elimination of all supervision.
    """
    validate_lexicon(lexicon)
    require(type(pairs) is list and 0 < len(pairs) <= 10000, "invalid_pair_collection")
    vocabulary = {t["surface"]: t for t in lexicon["tokens"]}
    seen = {}
    output = []
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"text", "meaning"}, "only_text_and_meaning_allowed")
        meaning = pair["meaning"]
        validate_meaning(meaning, lexicon["slot_candidates"])
        tokens = tokenize(pair["text"], vocabulary)
        require(pair["text"] not in seen or seen[pair["text"]] == canonical(meaning), "contradictory_duplicate_text")
        seen[pair["text"]] = canonical(meaning)
        sequence, used, first = [], set(), None
        for surface in tokens:
            token = vocabulary[surface]
            if token["kind"] == "marker":
                sequence.append(canonical(["literal", surface]))
            else:
                roles = [r for r in CONTENT if meaning[r] == token["value"]]
                require(len(roles) == 1 and roles[0] not in used, "ambiguous_or_repeated_alignment")
                role = roles[0]
                used.add(role)
                first = first or role
                sequence.append(canonical(["slot", role]))
        require(used == set(CONTENT) and first in GOALS, "incomplete_or_unsupported_alignment")
        output.append({"meaning": dict(meaning), "goal": first, "sequence": sequence})
    return output


class Space:
    def __init__(self, book, use_prefix=True, use_status=True):
        self.book, self.use_prefix, self.use_status = book, use_prefix, use_status
        self.cache = {}

    def context(self, meaning, goal, prefix=None):
        result = {"goal": goal}
        if self.use_status:
            result.update({r: meaning[r] for r in ("polarity", "modality")})
        if prefix is not None:
            result["prefix"] = list(prefix) if self.use_prefix else []
        return result

    def key(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            value = np.ones(self.book.dimension, dtype=np.complex128)
            for field in sorted(description):
                if field == "prefix":
                    value *= self.book.code("prefix_boundary", "present")
                    for i, symbol in enumerate(description[field]):
                        value *= np.roll(self.book.code("emitted_symbol", symbol), 17 * i)
                else:
                    value *= self.book.code("context_" + field, description[field])
            self.cache[identity] = value
        return self.cache[identity]
