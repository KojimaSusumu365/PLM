"""Training API takes pairs/lexical prior, never old readers or writer traces."""
from .algebra import Book, canonical, digest, require
from .features import aligned_examples, Space, END
from .memory import fit_memory
from .runtime import Writer


def fit(pairs, lexicon, *, seed="writer-development-0", dimension=8192,
        pair_learning=True, use_prefix=True, use_status=True):
    require(all(type(v) is bool for v in (pair_learning, use_prefix, use_status)), "invalid_switches")
    examples = aligned_examples(pairs, lexicon)
    space = Space(Book(dimension, seed), use_prefix, use_status)
    rows = {"support": [], "steps": [], "lexical": []}
    for example in examples:
        meaning, goal, sequence = example["meaning"], example["goal"], example["sequence"]
        rows["support"].append((space.context(meaning, goal), "supported"))
        for i, symbol in enumerate(sequence + [END]):
            rows["steps"].append((space.context(meaning, goal, sequence[:i]), symbol))
    for token in lexicon["tokens"]:
        if token["kind"] != "marker":
            rows["lexical"].append(({"lexical_value": token["value"]}, token["surface"]))
    memories, stats = {}, {}
    for name, observations in rows.items():
        memories[name], stats[name] = fit_memory(space, observations, name == "lexical" or pair_learning)
    metadata = {"schema": "plm-l1-pair-writer-v1", "dimension": dimension, "seed": seed,
                "use_prefix": use_prefix, "use_status": use_status, "pair_learning": pair_learning,
                "pair_count": len(pairs), "pairs_digest": digest(sorted(pairs, key=canonical)),
                "lexicon_digest": digest(lexicon), "slot_candidates": lexicon["slot_candidates"],
                "surfaces": {t["surface"]: t["kind"] for t in lexicon["tokens"]},
                "statistics": stats, "supervision_fields": ["text", "meaning"],
                "supplied_trace_supervision": False, "automatic_alignment": True,
                "eligible_for_inference": False}
    return Writer(metadata, memories)
