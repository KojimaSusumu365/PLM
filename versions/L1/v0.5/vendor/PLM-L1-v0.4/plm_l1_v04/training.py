"""Only text/meaning pairs and explicit initial lexicon enter this learner."""
from .algebra import Book, canonical, digest, require
from .features import observations
from .projection import Space, fit_memory
from .runtime import Model


def fit(pairs, lexicon, *, seed="parts-development-0", dimension=8192, partial=True, learning=True):
    require(type(partial) is bool and type(learning) is bool, "invalid_switches")
    rows = observations(pairs, lexicon)
    space = Space(Book(dimension, seed))
    memories, statistics = {}, {}
    for name, values in rows.items():
        memories[name], statistics[name] = fit_memory(space, values, partial, learning or name.startswith("lexical_"))
    meta = {"schema": "plm-l1-parts-v1", "seed": seed, "dimension": dimension, "partial": partial, "learning": learning,
            "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)), "lexicon_digest": digest(lexicon),
            "kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"],
            "statistics": statistics, "supervision_fields": ["text", "meaning"], "supplied_trace_supervision": False,
            "dependency_selection": "deterministic categorical information gain during training only", "eligible_for_inference": False}
    return Model(meta, memories)
