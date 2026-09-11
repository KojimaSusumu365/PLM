"""Learned SS action/next-state memory; recurrent state is a phase signal.

An explicit interpreter still dispatches lexical actions and emits characters.
Training sequences are NOT present in the saved inference artifact.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.banked import FreshBook
from plm_l1_v09.component.algebra import require, canonical
from .codecs import choose

class Program:
    def __init__(self, metadata, weights, engine):
        self.meta, self.weights, self.engine = metadata, weights, engine
        require(set(metadata) == {'schema', 'name', 'dimension', 'seed', 'actions', 'states', 'fields'}, 'program_metadata')
        require(metadata['schema'] == 'ss-wave-program-03' and weights.shape == (2, metadata['dimension']) and np.isfinite(weights).all(), 'program_weights')
        self.book = FreshBook(metadata['dimension'], metadata['seed'])
        self.actions = np.array([self.book.code('action', a) for a in metadata['actions']])
        self.states = np.array([self.book.code('state', i) for i in range(metadata['states'])])
        self.basis = np.broadcast_to(np.concatenate([self.actions, self.states])[None, :, :], (2, len(self.actions)+len(self.states), metadata['dimension']))

    def context(self, fields):
        require(sorted(fields) == self.meta['fields'], 'program_context')
        v = np.ones(self.meta['dimension'], complex)
        for key in self.meta['fields']:
            v *= self.book.code('context/'+key, fields[key])
        return v

    def start(self):
        return self.states[0].copy()

    def step(self, fields, state):
        require(isinstance(state, np.ndarray) and state.shape == (self.meta['dimension'],), 'state_signal')
        key = self.context(fields)*state
        scores = self.engine.correlate(self.weights, self.basis, self.meta['name']+'/step', np.broadcast_to(key, self.weights.shape))
        ai, aa = choose(scores[0, :len(self.actions)], 'unresolved_action')
        si, sa = choose(scores[1, len(self.actions):], 'unresolved_next_state')
        # Cleanup returns a phase signal; no integer program counter feeds the next read.
        return self.meta['actions'][ai], self.states[si].copy(), {'action_support': aa, 'state_support': sa, 'state_signal_sha256': hashlib.sha256(self.states[si].tobytes()).hexdigest()}

    def save(self, directory):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=False)
        np.savez_compressed(path/'weights.npz', weights=self.weights)
        envelope = {'metadata': self.meta, 'weights_sha256': hashlib.sha256(self.weights.astype('<c16').tobytes()).hexdigest()}
        (path/'program.json').write_text(canonical(envelope)+'\n', encoding='utf-8')

    @classmethod
    def load(cls, directory, engine):
        path = Path(directory)
        require({p.name for p in path.iterdir()} == {'program.json', 'weights.npz'}, 'program_inventory')
        data = json.loads((path/'program.json').read_text(encoding='utf-8'))
        require(set(data) == {'metadata', 'weights_sha256'}, 'program_envelope')
        with np.load(path/'weights.npz', allow_pickle=False) as arrays:
            require(arrays.files == ['weights'], 'program_array_inventory')
            weights = arrays['weights']
        require(hashlib.sha256(weights.astype('<c16').tobytes()).hexdigest() == data['weights_sha256'], 'program_hash')
        return cls(data['metadata'], weights, engine)
