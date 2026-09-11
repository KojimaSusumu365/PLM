"""Only text/meaning pairs and explicit initial lexicon enter this learner."""
from .algebra import Book, canonical, digest, require
from .features import observations
from .banked import fit_banked
from .runtime import Model
from ..selection import select
from ..thresholds import values as threshold_values


def fit(pairs, lexicon, *, seed="banked-development-0", dimension=8192, partial=True, learning=True, memory_mode="split_proof", selector="ss", selection_dimension=2048, selection_seed="selection-development-0", selection_enabled=True):
    require(type(partial) is bool and type(learning) is bool, "invalid_switches")
    require(type(selection_seed) is str and 0<len(selection_seed)<=64, 'invalid_selection_seed')
    rows = observations(pairs, lexicon)
    Book(dimension, seed)
    memories, statistics, audits = {}, {}, {}
    for name, values in rows.items():
        leaves, audits[name] = select(values, method=selector if partial else 'full', dimension=selection_dimension, seed=selection_seed+'/'+name, enabled=selection_enabled)
        memories[name], statistics[name] = fit_banked(values, dimension, seed, partial=partial, enabled=learning or name.startswith("lexical_"), mode=memory_mode, selected_leaves=leaves)
        statistics[name].pop('owned_heap_bytes')
    meta = {"schema": "plm-l1-component-v09", "memory_mode": memory_mode, "read_acceptance": "recover_equals_candidate_v1", "seed": seed, "dimension": dimension, "partial": partial, "learning": learning,
            "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)), "lexicon_digest": digest(lexicon),
            "kinds": {t["surface"]: t["kind"] for t in lexicon["tokens"]}, "slot_candidates": lexicon["slot_candidates"],
            "statistics": statistics, "supervision_fields": ["text", "meaning"], "supplied_trace_supervision": False,
            "dependency_selection": selector, "selector_dimension": selection_dimension, "selector_seed": selection_seed,
            "selector_enabled": selection_enabled, "thresholds": threshold_values(),
            "eligible_for_inference": False}
    model = Model(meta, memories)
    model.selection_audit = audits
    return model
