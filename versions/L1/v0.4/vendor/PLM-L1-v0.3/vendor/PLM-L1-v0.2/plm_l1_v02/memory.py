"""Balanced Hebbian phase association using compositional sequence keys."""
import numpy as np
from .compat import canonical, require


class Association:
    def __init__(self, space, vector, candidates, minimum=.65, margin=.25):
        self.space = space
        self.vector = np.asarray(vector, dtype=np.complex128).copy()
        require(self.vector.shape == (space.book.dimension,) and np.isfinite(self.vector).all(), "invalid association weights")
        self.candidates = tuple(sorted(set(candidates)))
        require(bool(self.candidates), "empty association candidates")
        self.basis = np.array([space.book.code("value", c).conj() for c in self.candidates])
        self.minimum, self.margin = minimum, margin
        self.cache = {}

    def recall(self, description):
        identity = canonical(description)
        if identity not in self.cache:
            query = self.vector * self.space.key(description)
            scores = np.real(self.basis @ query) / self.space.book.dimension
            order = np.argsort(-scores, kind="stable")
            top = float(scores[order[0]])
            runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
            accepted = top >= self.minimum and top - runner >= self.margin
            self.cache[identity] = {"value": self.candidates[order[0]] if accepted else None,
                                    "score": round(top, 8), "margin": round(top - runner, 8)}
        return dict(self.cache[identity])


def fit_association(space, observations, enabled=True):
    groups, candidates = {}, set()
    for description, target in observations:
        identity = canonical(description)
        if identity not in groups:
            groups[identity] = [description, {}]
        counts = groups[identity][1]
        counts[target] = counts.get(target, 0) + 1
        candidates.add(target)
    require(bool(groups), "empty paired observations")
    require(len(groups) <= 256, "association_context_capacity_exceeded")
    vector = np.zeros(space.book.dimension, dtype=np.complex128)
    if enabled:
        for identity in sorted(groups):
            description, counts = groups[identity]
            total = sum(counts.values())
            mean_value = sum(space.book.code("value", label) * (count / total) for label, count in sorted(counts.items()))
            vector += space.key(description).conj() * mean_value
    stats = {"contexts": len(groups), "observations": len(observations),
             "conflicting_contexts": sum(len(row[1]) > 1 for row in groups.values())}
    return Association(space, vector, candidates), stats
