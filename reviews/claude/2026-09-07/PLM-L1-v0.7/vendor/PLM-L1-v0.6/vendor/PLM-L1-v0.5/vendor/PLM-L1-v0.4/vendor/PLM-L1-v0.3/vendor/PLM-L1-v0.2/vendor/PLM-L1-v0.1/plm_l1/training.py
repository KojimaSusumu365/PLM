"""Supervised fitting; separate from inference, teacher and held-out labels."""
from .algebra import Book, learn, digest
from .teacher import lexicon, examples, reader_trace, writer_trace, GOALS
from .runtime import Model, reader_key, writer_key


def fit(seed="development-0", dimension=8192, *, learning=True, order_binding=True, role_binding=True):
    book = Book(dimension, seed)
    pairs = {k: [] for k in ("lex_class", "lex_value", "surface", "read_action", "read_next", "write_action")}
    vocabulary = lexicon()
    for surface, category, value in vocabulary:
        parts = [("token", surface)]
        pairs["lex_class"].append((parts, category))
        pairs["lex_value"].append((parts, value))
        pairs["surface"].append(([("meaning", value)], surface))
    records = list(examples("train"))
    for row in records:
        for state, token, category, action, nxt in reader_trace(row):
            parts = reader_key(state, category, order_binding)
            pairs["read_action"].append((parts, action))
            pairs["read_next"].append((parts, nxt))
        for goal in GOALS:
            for position, action in writer_trace(row, goal):
                parts = writer_key(goal, position, row["slots"]["polarity"], row["slots"]["modality"], order_binding)
                pairs["write_action"].append((parts, action))
    memories, stats = {}, {}
    for name in pairs:
        memories[name], stats[name] = learn(book, pairs[name], learning)
    candidates = {
        "subject": [v for _, c, v in vocabulary if c == "ENTITY"],
        "object": [v for _, c, v in vocabulary if c == "ENTITY"],
        "predicate": [v for _, c, v in vocabulary if c == "PREDICATE"],
        "polarity": ["polarity:positive", "polarity:negative"],
        "modality": ["modality:asserted", "modality:hypothetical"],
    }
    metadata = {"schema": "plm-l1-model-v1", "dimension": dimension, "seed": seed,
                "learning": learning, "order_binding": order_binding, "role_binding": role_binding,
                "token_surfaces": sorted(s for s, _, _ in vocabulary if s != "<EOS>"),
                "slot_candidates": candidates, "training_count": len(records),
                "training_digest": digest(records), "memory_statistics": stats,
                "minimum": 0.60, "margin": 0.25, "max_tokens": 10, "max_generation_steps": 10,
                "initial_state": "A0", "terminal_state": "DONE", "goals": list(GOALS),
                "eligible_for_inference": False}
    return Model(metadata, memories)
