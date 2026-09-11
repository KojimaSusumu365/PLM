"""Prediction-only runtime. No teacher history, exact table (except control), or replay."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require

LABELS = list('0123')
FIELDS = ['f0', 'f1', 'f2', 'f3']
# readers, reader dimension, shared residual, pair-check dimension
SPECS = {'single128': (1, 128, False, 0), 'single512': (1, 512, False, 0),
         'concat512': (4, 128, True, 0), 'multi4': (4, 128, False, 0),
         'clone4': (4, 128, False, 0), 'checked': (3, 128, False, 512),
         'exact': (1, 0, False, 0)}


def policy(threshold=.5, quorum=0, check_threshold=None, reject_all=False):
    return {'threshold': threshold, 'quorum': quorum, 'check_threshold': check_threshold,
            'reject_all': reject_all}


def validate_policy(p, banks, has_check):
    require(type(p) is dict and set(p) == {'threshold', 'quorum', 'check_threshold', 'reject_all'}, 'policy_schema')
    require(type(p['threshold']) in (int, float) and np.isfinite(p['threshold']) and 0 < p['threshold'] <= 2, 'policy_threshold')
    require(type(p['quorum']) is int and 0 <= p['quorum'] <= banks, 'policy_quorum')
    t = p['check_threshold']
    require(t is None or (has_check and type(t) in (int, float) and np.isfinite(t) and 0 < t <= 2), 'policy_checker')
    require(type(p['reject_all']) is bool, 'policy_reject_all')


def decide(raw, p):
    readers = np.asarray(raw['readers'], dtype=float)
    checker = np.asarray(raw['checker'], dtype=float)
    require(readers.ndim == 3 and readers.shape[1] >= 1 and readers.shape[2] == 4, 'reader_scores_shape')
    require(checker.shape in ((len(readers), 0), (len(readers), 4)), 'check_scores_shape')
    require(np.isfinite(readers).all() and np.isfinite(checker).all(), 'nonfinite_scores')
    validate_policy(p, readers.shape[1], checker.shape[1] == 4)
    mean = readers.mean(axis=1)
    order = np.argsort(-mean, axis=1, kind='stable')
    ix = np.arange(len(mean)); top = order[:, 0]
    gap = mean[ix, top] - mean[ix, order[:, 1]]
    tentative = np.where(gap > 1e-12, top, -1)
    hits = mean >= p['threshold']
    count = hits.sum(axis=1)
    accepted = np.where((count == 1) & (tentative >= 0), top, -1)
    reason = np.where(count == 0, 'no_support', np.where(count > 1, 'conflicting_support', 'accepted')).astype(object)
    bank_hits = readers >= .5
    bank_label = readers.argmax(axis=2)
    supports = ((bank_hits.sum(axis=2) == 1) & (bank_label == top[:, None])).sum(axis=1)
    bad = (accepted >= 0) & (supports < p['quorum'])
    accepted[bad] = -1; reason[bad] = 'bank_disagreement'
    if p['check_threshold'] is not None:
        ch = checker >= p['check_threshold']
        ok = (ch.sum(axis=1) == 1) & (checker.argmax(axis=1) == top)
        bad = (accepted >= 0) & ~ok
        accepted[bad] = -1; reason[bad] = 'check_rejected'
    if p['reject_all']:
        accepted[:] = -1; reason[:] = 'calibration_no_feasible_acceptance'
    return {'tentative': tentative, 'accepted': accepted, 'reason': reason,
            'mean': mean, 'margin': gap, 'supporting_banks': supports}


class Model:
    def __init__(self, architecture='single512', seed='code-0', readers=None, checker=None, entries=None, acceptance=None):
        require(architecture in SPECS and type(seed) is str and 0 < len(seed) <= 80, 'architecture_seed')
        self.architecture = architecture; self.seed = seed
        k, d, _, cd = SPECS[architecture]
        self.readers = np.zeros((k, 4, d), dtype=np.complex128) if readers is None else np.array(readers, copy=True)
        self.checker = np.zeros(cd, dtype=np.complex128) if checker is None else np.array(checker, copy=True)
        require(self.readers.shape == (k, 4, d) and self.readers.dtype == np.complex128 and np.isfinite(self.readers).all(), 'reader_weights')
        require(self.checker.shape == (cd,) and self.checker.dtype == np.complex128 and np.isfinite(self.checker).all(), 'checker_weights')
        self.entries = copy.deepcopy(entries or {})
        require(type(self.entries) is dict and (architecture == 'exact' or not self.entries), 'no_ss_key_table')
        for key, label in self.entries.items():
            self.validate(json.loads(key)); require(label in LABELS, 'invalid_exact_label')
        self.acceptance = copy.deepcopy(acceptance if acceptance is not None else policy(check_threshold=.5 if cd else None))
        validate_policy(self.acceptance, k, cd > 0)
        # concat512 and multi4 use exactly the same four independently generated blocks.
        self.books = [Book(d, f'multicode-01/{seed}/reader/{0 if architecture == "clone4" else i}/d{d}') for i in range(k)]
        self.check_book = Book(cd, f'multicode-01/{seed}/pair-check') if cd else None
        self.refresh()

    @staticmethod
    def validate(context):
        require(type(context) is dict and sorted(context) == FIELDS and
                all(type(v) is str and v in list('01234567') for v in context.values()), 'complete_known_vocabulary_context_required')

    def vectors(self, contexts):
        for c in contexts: self.validate(c)
        k, d, _, cd = SPECS[self.architecture]
        if self.architecture == 'exact': return np.empty((len(contexts), k, 0)), np.empty((len(contexts), 4, 0))
        b = np.array([[book.vector(c, FIELDS, 'product')[0] for book in self.books] for c in contexts], dtype=np.complex128).reshape(len(contexts), k, d)
        if cd:
            cb = np.array([self.check_book.vector(c, FIELDS, 'product')[0] for c in contexts], dtype=np.complex128).reshape(len(contexts), cd)
            labels = np.array([self.check_book.atom('__label__', y) for y in LABELS])
            z = cb[:, None, :] * labels[None, :, :]
        else: z = np.empty((len(contexts), 4, 0), dtype=np.complex128)
        return b, z

    def raw(self, contexts):
        for c in contexts: self.validate(c)
        if self.architecture == 'exact':
            r = np.array([[int(y == self.entries.get(canonical(c))) for y in LABELS] for c in contexts], dtype=float).reshape(len(contexts), 1, 4)
            return {'readers': r, 'checker': np.empty((len(contexts), 0))}
        b, z = self.vectors(contexts)
        d = self.readers.shape[2]
        r = np.einsum('nkd,kyd->nky', b, self.readers.conj()).real / d
        ch = (z @ self.checker.conj()).real / len(self.checker) if len(self.checker) else np.empty((len(contexts), 0))
        return {'readers': r, 'checker': ch}

    def predict(self, contexts):
        raw = self.raw(contexts); ds = decide(raw, self.acceptance)
        return [{'tentative': LABELS[t] if t >= 0 else None, 'accepted': LABELS[a] if a >= 0 else None,
                 'reason': str(reason), 'scores': ds['mean'][i].tolist(), 'reader_scores': raw['readers'][i].tolist(),
                 'check_scores': raw['checker'][i].tolist(), 'supporting_banks': int(ds['supporting_banks'][i]),
                 'score_is_probability': False, 'eligible_for_inference': False}
                for i, (t, a, reason) in enumerate(zip(ds['tentative'], ds['accepted'], ds['reason']))]

    def refresh(self):
        require(np.isfinite(self.readers).all() and np.isfinite(self.checker).all(), 'nonfinite_update')
        self.metadata = {'schema': 'plm-ss-multicode-model-01', 'architecture': self.architecture, 'seed': self.seed,
                         'acceptance': self.acceptance, 'entries': self.entries, 'eligible_for_inference': False}
        self.fingerprint = digest([self.metadata, hashlib.sha256(self.readers.astype('<c16').tobytes()).hexdigest(),
                                   hashlib.sha256(self.checker.astype('<c16').tobytes()).hexdigest()])

    def storage(self):
        books = self.books + ([self.check_book] if self.check_book else [])
        return {'coefficient_bytes': self.readers.nbytes + self.checker.nbytes,
                'reader_coefficient_bytes': self.readers.nbytes, 'checker_coefficient_bytes': self.checker.nbytes,
                'warm_atom_bytes': sum(a.nbytes for b in books for a in b.cache.values()),
                'metadata_utf8_bytes': len(canonical(self.metadata).encode('utf-8')), 'exact_entries': len(self.entries),
                'replay_entries': 0, 'scope': 'Owned arrays/serialized metadata; not peak RSS, power or full FLOPs.'}

    def save(self, directory):
        p = Path(directory); p.mkdir(parents=True, exist_ok=False)
        with (p / 'model.json').open('x', encoding='utf-8') as f:
            json.dump({'metadata': self.metadata, 'fingerprint': self.fingerprint}, f, ensure_ascii=False, indent=2)
        np.savez(p / 'weights.npz', readers=self.readers, checker=self.checker)

    @classmethod
    def load(cls, directory):
        p = Path(directory); require({f.name for f in p.iterdir()} == {'model.json', 'weights.npz'}, 'model_inventory')
        obj = json.loads((p / 'model.json').read_text(encoding='utf-8')); m = obj['metadata']
        require(m['schema'] == 'plm-ss-multicode-model-01' and m['eligible_for_inference'] is False, 'model_contract')
        with np.load(p / 'weights.npz', allow_pickle=False) as z:
            require(z.files == ['readers', 'checker'], 'array_inventory')
            model = cls(m['architecture'], m['seed'], z['readers'], z['checker'], m['entries'], m['acceptance'])
        require(model.metadata == m and model.fingerprint == obj['fingerprint'], 'model_fingerprint')
        return model
