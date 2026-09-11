"""Comparison-only two-lane codec; SAME dimension and per-binding energy.

Entity roles receive half the coordinates. All other roles occupy the rest.
Each binding is scaled by sqrt(D/lane_length); no role/state information dropped.
"""
import numpy as np
from plm_p1.core import validate_frames, address, validate_symbol


def template(book, document_id, event_id, role, value):
    validate_symbol(value)
    d = book.dimension
    lane = slice(0, d // 2) if role in {"subject", "object"} else slice(d // 2, d)
    vector = np.zeros(d, complex)
    vector[lane] = (book.key(document_id, event_id, role) * book.value(value))[lane] * np.sqrt(2)
    return vector


def encode_partitioned(frames, book):
    validate_frames(frames)
    y = np.zeros(book.dimension, complex)
    for frame in sorted(frames, key=lambda f: address(f["document_id"], f["event_id"])):
        for role, value in sorted(frame["slots"].items()):
            y += template(book, frame["document_id"], frame["event_id"], role, value)
    return y
