"""Training-only key witnesses: phase superposition or an exact matched control."""
import numpy as np
from plm_l1_v011.algebra import Book, canonical, require

SUPPORT_THRESHOLD = 0.5


class EvidenceMemory:
    def __init__(self, fields, labels, dimension, seed, backend, weights, entries, key_counts):
        self.fields = list(fields)
        self.labels = list(labels)
        self.dimension = dimension
        self.seed = seed
        self.backend = backend
        self.weights = weights
        self.entries = entries
        self.key_counts = key_counts
        self.book = Book(dimension, seed)

    def scores(self, context):
        require(set(context) == set(self.fields), 'witness_requires_complete_selected_key')
        key = canonical([[f, context[f]] for f in self.fields])
        if self.backend == 'exact':
            return np.array(self.entries.get(key, [0] * len(self.labels)), dtype=float)
        q, _ = self.book.vector(context, self.fields, 'product')
        return (self.weights.conj() @ q).real / self.dimension

    def assess(self, context, label):
        scores = self.scores(context)
        hits = [y for y, s in zip(self.labels, scores) if s >= SUPPORT_THRESHOLD]
        return {'supported': hits == [label], 'hits': hits,
                'scores': [float(s) for s in scores]}

    def metadata(self):
        return {'fields': self.fields, 'labels': self.labels, 'dimension': self.dimension,
                'seed': self.seed, 'backend': self.backend, 'entries': self.entries,
                'key_counts': self.key_counts, 'threshold': SUPPORT_THRESHOLD}


def build_evidence(rows, fields, labels, dimension, seed, backend):
    # Deduplication is training-time control. SS inference retains no key table.
    entries = {}
    for row in rows:
        key = canonical([[f, row['context'][f]] for f in fields])
        entries.setdefault(key, [0] * len(labels))[labels.index(row['label'])] = 1
    counts = [sum(v[i] for v in entries.values()) for i in range(len(labels))]
    weights = np.zeros((len(labels), dimension), dtype=np.complex128) if backend == 'ss' else np.zeros((0, 0), dtype=np.complex128)
    if backend == 'ss':
        import json
        book = Book(dimension, seed)
        for key, present in sorted(entries.items()):
            q, _ = book.vector(dict(json.loads(key)), fields, 'product')
            for i, exists in enumerate(present):
                if exists:
                    weights[i] += q
    return EvidenceMemory(fields, labels, dimension, seed, backend, weights,
                          entries if backend == 'exact' else {}, counts)
