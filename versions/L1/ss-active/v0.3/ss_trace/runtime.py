"""Teacher-free SS runtime. No exact key-label map or teacher replay buffer."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from ss_multicode.algebra import Book, canonical, digest, require
from ss_multicode.model import Model, FIELDS, LABELS, decide, policy

ARMS = {
    'main512': (128, 'none'),
    'main640': (160, 'none'),
    'main384': (96, 'none'),
    'main512_pair': (128, 'pair'),
    'main384_pair': (96, 'pair'),
    'main512_bank': (128, 'bank'),
}
TRACE_D = {'none': 0, 'pair': 128, 'bank': 32}
COOLDOWN = 64
DROP = .15
TRACE_MARGIN = .15


def context_id(c):
    Model.validate(c)
    return digest(['ss-active-context-01', c])


def choice(raw):
    return decide({'readers': raw, 'checker': np.empty((len(raw), 0))}, policy())


def binary_stats(target, alarm):
    target = np.asarray(target, bool); alarm = np.asarray(alarm, bool)
    require(target.shape == alarm.shape, 'binary_shape')
    tp = int((target & alarm).sum()); fp = int((~target & alarm).sum())
    fn = int((target & ~alarm).sum()); tn = int((~target & ~alarm).sum())
    return {'n': int(target.size), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None}


def diagnostics(main, auxiliary, ids, ledger, step):
    """Only current correlations and label-free ledger enter this decision."""
    m = choice(main); n = len(ids)
    eligible = np.array([key in ledger and step-ledger[key]['last_step'] >= COOLDOWN for key in ids])
    post = np.array([ledger[key]['post_margin'] if key in ledger else 0. for key in ids])
    gap_drop = eligible & (post-m['margin'] >= DROP)
    out = {'main_tentative': m['tentative'], 'main_accepted': m['accepted'],
           'main_margin': m['margin'], 'eligible': eligible, 'gap_drop': gap_drop,
           'aux_accepted': np.full(n, -1, int), 'aux_confident': np.zeros(n, bool),
           'ss_disagreement': np.zeros(n, bool), 'ss_weak_support': np.zeros(n, bool),
           'priority': np.full(n, -1e30)}
    if auxiliary.shape[1] == 0:
        return out
    a = choice(auxiliary)
    confident = (a['accepted'] >= 0) & (a['margin'] >= TRACE_MARGIN)
    ix = np.arange(n); y = np.maximum(a['accepted'], 0)
    others = m['mean'].copy(); others[ix, y] = -np.inf
    support = m['mean'][ix, y] - others.max(axis=1)
    out.update(aux_accepted=a['accepted'], aux_confident=confident,
               ss_disagreement=eligible & confident & (m['tentative'] != a['accepted']),
               ss_weak_support=eligible & confident & (support <= TRACE_MARGIN),
               priority=np.where(eligible & confident, -support, -1e30))
    return out


class State:
    def __init__(self, arm='main512_pair', seed='active3-code-0', main=None, auxiliary=None,
                 step=0, acquired=0, history=None, ledger=None):
        require(arm in ARMS and type(seed) is str and 0 < len(seed) <= 80, 'arm_seed')
        require(type(step) is int and type(acquired) is int and 0 <= acquired <= step, 'counters')
        self.arm = arm; self.seed = seed; self.d, self.kind = ARMS[arm]
        td = TRACE_D[self.kind]
        self.main = np.zeros((4, 4, self.d), complex) if main is None else np.array(main, copy=True)
        ashape = (4, td) if self.kind == 'pair' else (4, 4, td)
        self.auxiliary = np.zeros(ashape, complex) if auxiliary is None else np.array(auxiliary, copy=True)
        require(self.main.shape == (4, 4, self.d) and self.main.dtype == np.complex128, 'main_shape')
        require(self.auxiliary.shape == ashape and self.auxiliary.dtype == np.complex128, 'aux_shape')
        require(np.isfinite(self.main).all() and np.isfinite(self.auxiliary).all(), 'finite_weights')
        self.step = step; self.acquired = acquired; self.history = history or digest(['active3-empty'])
        require(type(self.history) is str and len(self.history) == 64, 'history_hash')
        self.ledger = copy.deepcopy(ledger or {})
        require(type(self.ledger) is dict and len(self.ledger) <= 512, 'ledger_size')
        for key, row in self.ledger.items():
            require(type(row) is dict and set(row) == {'context', 'last_step', 'post_margin', 'visits'}, 'label_free_ledger')
            require(context_id(row['context']) == key, 'ledger_context')
            require(type(row['last_step']) is int and 1 <= row['last_step'] <= step, 'ledger_step')
            require(type(row['visits']) is int and row['visits'] >= 1, 'ledger_visits')
            require(type(row['post_margin']) in (float, int) and np.isfinite(row['post_margin']) and row['post_margin'] >= 0, 'ledger_margin')
        require(sum(r['visits'] for r in self.ledger.values()) == acquired, 'ledger_count')
        self.books = [Book(self.d, f'multicode-01/{seed}/reader/{i}/d{self.d}') for i in range(4)]
        self.aux_books = [Book(td, f'active3-trace/{seed}/{self.kind}/{i}/d{td}') for i in range(4)] if td else []

    def vectors(self, contexts, auxiliary=False):
        for c in contexts: Model.validate(c)
        books = self.aux_books if auxiliary else self.books
        d = TRACE_D[self.kind] if auxiliary else self.d
        return np.array([[b.vector(c, FIELDS, 'product')[0] for b in books] for c in contexts],
                        dtype=complex).reshape(len(contexts), len(books), d)

    def pair_vectors(self, contexts):
        b = self.vectors(contexts, True)
        y = np.array([[book.atom('__label__', label) for label in LABELS] for book in self.aux_books])
        return b[:, :, None, :] * y[None, :, :, :]

    def raw(self, contexts):
        b = self.vectors(contexts)
        main = np.einsum('nkd,kyd->nky', b, self.main.conj()).real / self.d
        if self.kind == 'pair':
            z = self.pair_vectors(contexts)
            aux = np.einsum('nkyd,kd->nky', z, self.auxiliary.conj()).real / TRACE_D[self.kind]
        elif self.kind == 'bank':
            b = self.vectors(contexts, True)
            aux = np.einsum('nkd,kyd->nky', b, self.auxiliary.conj()).real / TRACE_D[self.kind]
        else:
            aux = np.empty((len(contexts), 0, 4))
        return main, aux

    def observe(self, contexts):
        main, aux = self.raw(contexts)
        d = diagnostics(main, aux, [context_id(c) for c in contexts], self.ledger, self.step)
        return [{'context_id': context_id(c), 'main_scores': main[i].mean(axis=0).tolist(),
                 'trace_scores': aux[i].mean(axis=0).tolist() if aux.shape[1] else [],
                 **{k: v[i].item() for k, v in d.items()},
                 'action': 'observe_only', 'score_is_probability': False, 'eligible_for_inference': False}
                for i, c in enumerate(contexts)]

    @property
    def metadata(self):
        return {'schema': 'plm-ss-active3-state', 'arm': self.arm, 'seed': self.seed,
                'step': self.step, 'acquired': self.acquired, 'history': self.history,
                'ledger': self.ledger, 'eligible_for_inference': False}

    @property
    def fingerprint(self):
        return digest([self.metadata, hashlib.sha256(self.main.astype('<c16').tobytes()).hexdigest(),
                       hashlib.sha256(self.auxiliary.astype('<c16').tobytes()).hexdigest()])

    def clone(self):
        obj = State(self.arm, self.seed, self.main, self.auxiliary, self.step, self.acquired, self.history, self.ledger)
        obj.books = self.books; obj.aux_books = self.aux_books
        return obj

    def storage(self):
        return {'main_coefficient_bytes': self.main.nbytes, 'trace_coefficient_bytes': self.auxiliary.nbytes,
                'total_coefficient_bytes': self.main.nbytes+self.auxiliary.nbytes,
                'warm_atom_bytes': sum(a.nbytes for b in self.books+self.aux_books for a in b.cache.values()),
                'metadata_utf8_bytes': len(canonical(self.metadata).encode('utf-8')),
                'ledger_entries': len(self.ledger), 'exact_teacher_label_entries': 0,
                'external_presentations': self.step, 'trace_updates': self.acquired if self.kind != 'none' else 0,
                'main_update_elements': self.step*self.main.size,
                'trace_update_elements': self.acquired*self.auxiliary.size,
                'scope': 'Owned coefficients, atom cache, serialized metadata. Not peak RSS or total FLOPs.'}

    def save(self, directory):
        p = Path(directory); p.mkdir(parents=True, exist_ok=False)
        (p/'state.json').write_text(canonical({'metadata': self.metadata, 'fingerprint': self.fingerprint})+'\n', encoding='utf-8')
        np.savez(p/'weights.npz', main=self.main, auxiliary=self.auxiliary)

    @classmethod
    def load(cls, directory):
        p = Path(directory)
        require({x.name for x in p.iterdir()} == {'state.json', 'weights.npz'}, 'state_inventory')
        obj = json.loads((p/'state.json').read_text(encoding='utf-8')); m = obj['metadata']
        require(set(m) == {'schema','arm','seed','step','acquired','history','ledger','eligible_for_inference'}, 'metadata_fields')
        require(m['schema'] == 'plm-ss-active3-state' and m['eligible_for_inference'] is False, 'state_contract')
        with np.load(p/'weights.npz', allow_pickle=False) as z:
            require(z.files == ['main','auxiliary'], 'weight_inventory')
            s = cls(m['arm'], m['seed'], z['main'], z['auxiliary'], m['step'], m['acquired'], m['history'], m['ledger'])
        require(s.metadata == m and s.fingerprint == obj['fingerprint'], 'state_fingerprint')
        return s
