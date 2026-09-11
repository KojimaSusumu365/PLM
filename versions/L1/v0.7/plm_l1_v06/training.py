"""Only text/meaning pairs and explicit initial lexicon enter this learner."""
from .algebra import Book, canonical, digest, require
from .features import observations
from .banked import fit_banked
from .runtime import Model


def fit(pairs, lexicon, *, seed="banked-development-0", dimension=8192, partial=True, learning=True, memory_mode="split_proof"):
    require(type(partial) is bool and type(learning) is bool, "invalid_switches")
    rows = observations(pairs, lexicon)
    Book(dimension, seed)
    memories, statistics = {}, {}
    for name, values in rows.items():
        memories[name], statistics[name] = fit_banked(values, dimension, seed, partial=partial, enabled=learning or name.startswith("lexical_"), mode=memory_mode)
    meta = {"schema": "plm-l1-banked-v1", "memory_mode": memory_mode, "read_acceptance": "recover_equals_candidate_v1", "seed": seed, "dimension": dimension, "partial": partial, "learning": learning,
            "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)), "lexicon_digest": digest(lexicon),
            "kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"],
            "statistics": statistics, "supervision_fields": ["text", "meaning"], "supplied_trace_supervision": False,
            "dependency_selection": "deterministic categorical information gain during training only", "eligible_for_inference": False}
    return Model(meta, memories)
