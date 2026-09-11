"""Balanced phase association; no context table retained after fitting."""
import numpy as np
from .algebra import canonical, require


class Association:
    def __init__(self, space, vector, candidates):
        self.space = space
        self.vector = np.asarray(vector, dtype=np.complex128).copy()
        require(self.vector.shape == (space.book.dimension,) and np.isfinite(self.vector).all(), "invalid_weights")
        self.candidates = tuple(sorted(set(candidates)))
        require(bool(self.candidates), "empty_candidates")
        self.basis = np.array([space.book.code("value", c).conj() for c in self.candidates])
        self.cache = {}

    def recall(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            scores = np.real(self.basis @ (self.vector * self.space.key(description))) / self.space.book.dimension
            order = np.argsort(-scores, kind="stable")
            top = float(scores[order[0]])
            runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
            self.cache[identity] = {"value": self.candidates[order[0]] if top >= .65 and top - runner >= .25 else None,
                                    "score": round(top, 8), "margin": round(top - runner, 8)}
        return dict(self.cache[identity])


def fit_memory(space, observations, enabled=True):
    groups, candidates = {}, set()
    for key, target in observations:
        identity = canonical(key)
        if identity not in groups:
            groups[identity] = [key, {}]
        counts = groups[identity][1]
        counts[target] = counts.get(target, 0) + 1
        candidates.add(target)
    require(0 < len(groups) <= 256, "association_capacity_exceeded")
    vector = np.zeros(space.book.dimension, dtype=np.complex128)
    if enabled:
        for identity in sorted(groups):
            key, counts = groups[identity]
            mean = sum(space.book.code("value", value) * (n / sum(counts.values())) for value, n in sorted(counts.items()))
            vector += space.key(key).conj() * mean
    return Association(space, vector, candidates), {"contexts": len(groups), "observations": len(observations),
             "conflicting_contexts": sum(len(row[1]) > 1 for row in groups.values())}
