"""Prediction-only SS/exact memory; SS saves no key table or fitted coefficients."""
import hashlib
import json
from pathlib import Path
import numpy as np
from plm_l1_v013.algebra import Book, canonical, digest


def decide(scores, labels, threshold=0.5):
    x = np.asarray(scores, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != len(labels) or not np.isfinite(x).all():
        raise ValueError('invalid_scores')
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError('invalid_threshold')
    result = []
    for row in x:
        hits = [y for y, value in zip(labels, row) if value >= threshold]
        result.append({'value': hits[0] if len(hits) == 1 else None,
                       'reason': 'accepted' if len(hits) == 1 else 'no_support' if not hits else 'conflicting_support',
                       'eligible_for_inference': False})
    return result


def vectors(book, contexts, fields):
    for c in contexts:
        if type(c) is not dict or sorted(c) != fields or not all(type(v) is str for v in c.values()):
            raise ValueError('invalid_context')
    return np.array([book.vector(c, fields, 'product')[0] for c in contexts])


class Memory:
    def __init__(self, metadata, weights):
        self.metadata = metadata
        self.weights = np.asarray(weights)
        self.validate()
        self.book = Book(metadata['dimension'], metadata['seed'])
        self.fingerprint = digest([metadata, hashlib.sha256(self.weights.astype('<c16').tobytes()).hexdigest()])

    def validate(self):
        m = self.metadata
        if m['schema'] != 'plm-ss-weighting-experiment-01' or m['eligible_for_inference'] is not False:
            raise ValueError('invalid_contract')
        if m['backend'] not in ('ss', 'exact') or m['fields'] != sorted(set(m['fields'])) or not m['fields']:
            raise ValueError('invalid_metadata')
        if m['labels'] != sorted(set(m['labels'])) or len(m['labels']) < 2 or m['threshold'] != 0.5:
            raise ValueError('invalid_labels_or_threshold')
        d = m['dimension']
        expected = (len(m['labels']), d) if m['backend'] == 'ss' else (0, 0)
        if type(d) is not int or not (8 <= d <= 4096 if m['backend'] == 'ss' else d == 0):
            raise ValueError('invalid_dimension')
        if self.weights.shape != expected or self.weights.dtype != np.complex128 or not np.isfinite(self.weights).all():
            raise ValueError('invalid_weights')
        if m['backend'] == 'ss' and m['entries']:
            raise ValueError('ss_cannot_store_key_table')
        if m['backend'] == 'exact' and any(y not in m['labels'] for y in m['entries'].values()):
            raise ValueError('invalid_exact_labels')

    def scores(self, contexts):
        if self.metadata['backend'] == 'ss':
            return (vectors(self.book, contexts, self.metadata['fields']) @ self.weights.conj().T).real / self.metadata['dimension']
        result = []
        for c in contexts:
            if type(c) is not dict or sorted(c) != self.metadata['fields'] or not all(type(v) is str for v in c.values()):
                raise ValueError('invalid_context')
            found = self.metadata['entries'].get(canonical(c))
            result.append([int(y == found) for y in self.metadata['labels']])
        return np.asarray(result, dtype=float)

    def predict(self, contexts):
        return decide(self.scores(contexts), self.metadata['labels'], self.metadata['threshold'])

    def storage(self):
        return {'weight_bytes': int(self.weights.nbytes), 'metadata_bytes': len(canonical(self.metadata).encode('utf-8')),
                'warm_atoms_bytes': sum(v.nbytes for v in self.book.cache.values()),
                'energy': float(np.sum(np.abs(self.weights) ** 2)),
                'scope': 'complex128 weights and UTF8 metadata; not total RAM or fixed-energy hardware.'}

    def save(self, directory):
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=False)
        (p / 'model.json').write_text(json.dumps({'metadata': self.metadata, 'fingerprint': self.fingerprint}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        np.savez(p / 'weights.npz', weights=self.weights)

    @classmethod
    def load(cls, directory):
        p = Path(directory)
        if {x.name for x in p.iterdir()} != {'model.json', 'weights.npz'}:
            raise ValueError('invalid_inventory')
        obj = json.loads((p / 'model.json').read_text(encoding='utf-8'))
        with np.load(p / 'weights.npz', allow_pickle=False) as z:
            if z.files != ['weights']:
                raise ValueError('invalid_arrays')
            model = cls(obj['metadata'], z['weights'].copy())
        if model.fingerprint != obj['fingerprint']:
            raise ValueError('fingerprint_mismatch')
        return model
