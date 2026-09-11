"""Deterministic unit phasors and Hebbian holographic associative memory.

No linguistic rules, original sentences, or training labels are consulted here.
"""
import hashlib
import json
import numpy as np


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def require(test, message):
    if not test:
        raise ValueError(message)


class Book:
    def __init__(self, dimension=8192, seed="development-0"):
        require(type(dimension) is int and 128 <= dimension <= 16384 and dimension % 64 == 0, "invalid dimension")
        require(type(seed) is str and 0 < len(seed) <= 128, "invalid seed")
        self.dimension, self.seed = dimension, seed
        self.cache = {}

    def code(self, namespace, value):
        key = canonical(["plm-l1-phase-u53-v1", self.seed, namespace, value])
        if key not in self.cache:
            raw = hashlib.shake_256(key.encode("utf-8")).digest(8 * self.dimension)
            phase = (np.frombuffer(raw, dtype="<u8") >> 11).astype(float) * (2.0 ** -53) * (2 * np.pi)
            vector = np.exp(1j * phase)
            vector.setflags(write=False)
            self.cache[key] = vector
        return self.cache[key]

    def key(self, parts):
        out = np.ones(self.dimension, dtype=np.complex128)
        for namespace, value in parts:
            out *= self.code(namespace, value)
        return out


class Memory:
    def __init__(self, book, vector, candidates, minimum=0.60, margin=0.25):
        self.book = book
        self.vector = np.asarray(vector, dtype=np.complex128).copy()
        require(self.vector.shape == (book.dimension,) and np.isfinite(self.vector).all(), "invalid memory")
        self.candidates = tuple(sorted(set(candidates)))
        require(bool(self.candidates), "empty candidates")
        self.basis = np.array([book.code("value", c).conj() for c in self.candidates])
        self.minimum, self.margin = minimum, margin
        self.cache = {}

    def recall(self, parts):
        identity = canonical(parts)
        if identity not in self.cache:
            query = self.vector * self.book.key(parts)
            scores = np.real(self.basis @ query) / self.book.dimension
            order = np.argsort(-scores, kind="stable")
            top = float(scores[order[0]])
            runner = max(0.0, float(scores[order[1]])) if len(order) > 1 else 0.0
            accepted = top >= self.minimum and top - runner >= self.margin
            self.cache[identity] = {
                "value": self.candidates[order[0]] if accepted else None,
                "score": round(top, 8), "margin": round(top - runner, 8),
                "reason": "recovered" if accepted else "weak_or_ambiguous_association",
            }
        return dict(self.cache[identity])


def learn(book, observations, enabled=True):
    """Balanced Hebbian association: H = sum_k conj(k) * mean(v | k).

    Counts are collected only during fitting; runtime retains H and vocabulary,
    never the context->label lookup. Repetitions do not inflate memory gain.
    """
    groups, candidates = {}, set()
    for parts, target in observations:
        key = canonical(parts)
        if key not in groups:
            groups[key] = [parts, {}]
        counts = groups[key][1]
        counts[target] = counts.get(target, 0) + 1
        candidates.add(target)
    require(bool(groups), "empty training observations")
    vector = np.zeros(book.dimension, dtype=np.complex128)
    if enabled:
        for key in sorted(groups):
            parts, counts = groups[key]
            total = sum(counts.values())
            target = sum((book.code("value", label) * (n / total) for label, n in sorted(counts.items())))
            vector += np.conj(book.key(parts)) * target
    stats = {"observations": sum(sum(x[1].values()) for x in groups.values()),
             "contexts": len(groups), "conflicting_contexts": sum(len(x[1]) > 1 for x in groups.values())}
    return Memory(book, vector, candidates), stats
