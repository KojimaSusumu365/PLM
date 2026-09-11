"""Strict sentence/meaning-pair reader training.

No teacher, oracle, reader trace, generator, or state/action label API is imported.
Alignment uses ONLY an explicitly supplied initial content lexicon and gold slot
values in each training pair. This remains supervised and lexically grounded.
"""
from .compat import Book, learn, canonical, digest, require
from .features import validate_lexicon, tokenize, abstract, descriptor, Space
from .memory import fit_association
from .runtime import PairReader


def observations(pairs, lexicon, ordered=True):
    validate_lexicon(lexicon)
    require(type(pairs) is list and 0 < len(pairs) <= 10000, "invalid pair collection")
    kinds = {t["surface"]: t["kind"] for t in lexicon["tokens"]}
    lexical = {t["surface"]: t["value"] for t in lexicon["tokens"] if t["value"] is not None}
    output = {"support": [], "roles": [], "states": []}
    meanings_by_text = {}
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"text", "meaning"}, "pairs accept only text and meaning; trace/order/state/action fields prohibited")
        meaning = pair["meaning"]
        require(type(meaning) is dict and set(meaning) == set(lexicon["slot_candidates"]), "invalid meaning fields")
        for role, value in meaning.items():
            require(value in lexicon["slot_candidates"][role], "meaning outside public candidates")
        tokens = tokenize(pair["text"], kinds)
        identity = pair["text"]
        require(identity not in meanings_by_text or meanings_by_text[identity] == canonical(meaning), "contradictory duplicate text")
        meanings_by_text[identity] = canonical(meaning)
        shape = abstract(tokens, kinds)
        output["support"].append((descriptor(shape, ordered=ordered), "supported"))
        # Derive token-role alignments from equality of lexical IDs and supplied
        # semantic values; no step-by-step parse labels or particle rules.
        aligned_positions = set()
        for role in ("subject", "object", "predicate"):
            positions = [i for i, token in enumerate(tokens) if lexical.get(token) == meaning[role]]
            require(len(positions) == 1, "ambiguous_or_missing_lexical_alignment")
            position = positions[0]
            require(position not in aligned_positions, "nonunique_role_alignment")
            aligned_positions.add(position)
            output["roles"].append((descriptor(shape, position=position, kind=kinds[tokens[position]], ordered=ordered), role))
        require(aligned_positions == {i for i, token in enumerate(tokens) if kinds[token] != "marker"}, "unexplained_content_token")
        for slot in ("polarity", "modality"):
            output["states"].append((descriptor(shape, slot=slot, ordered=ordered), meaning[slot]))
    return output


def fit(pairs, lexicon, *, seed="pair-development-0", dimension=8192, pair_learning=True, ordered=True):
    require(type(pair_learning) is bool and type(ordered) is bool, "invalid ablation switches")
    rows = observations(pairs, lexicon, ordered)
    book = Book(dimension, seed)
    space = Space(book, ordered)
    memories, statistics = {}, {}
    for name in rows:
        memories[name], statistics[name] = fit_association(space, rows[name], pair_learning)
    lexical_pairs = [([("token", t["surface"])], t["value"]) for t in lexicon["tokens"] if t["value"] is not None]
    lexical, lexical_stats = learn(book, lexical_pairs)
    metadata = {"schema": "plm-l1-pair-reader-v1", "seed": seed, "dimension": dimension,
                "ordered": ordered, "pair_learning": pair_learning,
                "token_kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]},
                "slot_candidates": lexicon["slot_candidates"], "lexicon_digest": digest(lexicon),
                "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)),
                "statistics": statistics, "lexical_prior_statistics": lexical_stats,
                "supervision_fields": ["text", "meaning"], "reader_trace_supervision": False,
                "minimum": .65, "margin": .25, "eligible_for_inference": False}
    return PairReader(metadata, memories, lexical)
