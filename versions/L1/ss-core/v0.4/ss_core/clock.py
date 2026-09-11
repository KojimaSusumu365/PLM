"""Causal read windows. The receiver API accepts only the current numeric tick.

The local port is an array-backed memory DAC *simulation*, not physical hardware.
Query/label references are public phase codes; learned coefficients arrive as samples.
Only finish() after a valid tail produces usable scores. peek() cannot do so.
"""
import hashlib
import numpy as np
from plm_l1_v09.component.algebra import require

PILOT = 16
POLICY = {'pilot_minimum':12, 'pilot_coherence':0.95, 'pilot_residual':0.10,
          'lookup_fraction':0.75, 'learning_fraction':1.0, 'illustrative_tick_hz':8000}


def weight_hash(part):
    return hashlib.sha256(part.weights.astype('<c16').tobytes()).hexdigest()


def references(part, key, nonce):
    require(part.kind == 'pair', 'pair_memory_only')
    require(type(nonce) is str and 0 < len(nonce) < 180, 'window_nonce')
    return np.array([[b.code('core-pilot', [key, nonce, side])[:PILOT]
                      for b in part.books] for side in ('head', 'tail')])


class ExactPort:
    """Exposes a single column at a time; no impairment/truth arguments."""
    def __init__(self, part, key, nonce):
        self.part = part
        self.pilots = references(part, key, nonce)
        self.length = part.dimension + 2 * PILOT

    def __iter__(self):
        for tick in range(self.length):
            if tick < PILOT:
                sample = self.pilots[0, :, tick]
            elif tick < PILOT + self.part.dimension:
                sample = self.part.weights[:, tick-PILOT]
            else:
                sample = self.pilots[1, :, tick-PILOT-self.part.dimension]
            yield tick, sample.copy(), np.ones(4, dtype=bool)


class ReadWindow:
    def __init__(self, part, key, nonce, learning=False):
        require(type(learning) is bool, 'learning_flag')
        self.part, self.key, self.learning = part, key, learning
        self.context = part.context(key)
        self.pilots = references(part, key, nonce)
        self.initial_hash = weight_hash(part)
        self.length = part.dimension + 2 * PILOT
        self.next_tick = 0
        self.failure = None
        self.acc = np.zeros((4, len(part.labels)), complex)
        self.counts = np.zeros(4, dtype=int)
        self.pilot_samples = np.zeros((2, 4, PILOT), complex)
        self.pilot_masks = np.zeros((2, 4, PILOT), bool)
        self.rotation = None
        self.head_audit = None
        self.tail_audit = None
        self.closed = False

    def fail(self, reason):
        self.failure = self.failure or reason

    def _pilot(self, side, estimate=False):
        y, ref, mask = self.pilot_samples[side], self.pilots[side], self.pilot_masks[side]
        counts = mask.sum(axis=1)
        z = (y * ref.conj() * mask).sum(axis=1)
        energy = (abs(y)**2 * mask).sum(axis=1)
        coherence = abs(z) / np.sqrt(np.maximum(energy * counts, 1e-30))
        if estimate:
            self.rotation = np.exp(-1j * np.angle(z))
        residual = np.sqrt((abs(y * self.rotation[:,None] - ref)**2 * mask).sum(axis=1)
                           / np.maximum(counts, 1))
        okay = bool(np.all(counts >= POLICY['pilot_minimum']) and
                    np.all(coherence >= POLICY['pilot_coherence']) and
                    np.all(residual <= POLICY['pilot_residual']))
        return {'accepted':okay, 'counts':counts.tolist(),
                'coherence':coherence.tolist(), 'residual':residual.tolist()}

    def push(self, tick, samples, observed):
        if self.closed:
            self.fail('read_after_close')
            return
        if self.failure:
            return
        if type(tick) is not int or tick != self.next_tick or tick >= self.length:
            self.fail('tick_order_or_length')
            return
        y, mask = np.asarray(samples), np.asarray(observed)
        if y.shape != (4,) or y.dtype.kind not in 'fc' or mask.shape != (4,) or mask.dtype != bool:
            self.fail('sample_contract')
            return
        if not np.isfinite(y).all() or np.any(y[~mask] != 0):
            self.fail('sample_nonfinite_or_missing_nonzero')
            return
        self.next_tick += 1
        if tick < PILOT:
            self.pilot_samples[0,:,tick] = y
            self.pilot_masks[0,:,tick] = mask
            if tick == PILOT-1:
                self.head_audit = self._pilot(0, estimate=True)
                if not self.head_audit['accepted']:
                    self.fail('head_pilot')
        elif tick < PILOT + self.part.dimension:
            j = tick-PILOT
            sample = y * self.rotation * self.context[:,j].conj()
            self.acc += self.part.values[:,:,j].conj() * sample[:,None]
            self.counts += mask
        else:
            j = tick-PILOT-self.part.dimension
            self.pilot_samples[1,:,j] = y
            self.pilot_masks[1,:,j] = mask
            if tick == self.length-1:
                self.tail_audit = self._pilot(1)
                if not self.tail_audit['accepted']:
                    self.fail('tail_pilot')

    def push_many(self, events):
        for event in events:
            self.push(*event)

    def peek(self):
        return {'status':'provisional', 'ticks_received':self.next_tick,
                'data_counts':self.counts.tolist(), 'failure':self.failure,
                'eligible_for_decision':False}

    def finish(self):
        if self.closed:
            self.fail('read_already_closed')
        self.closed = True
        if self.next_tick != self.length:
            self.fail('incomplete_window')
        if weight_hash(self.part) != self.initial_hash:
            self.fail('memory_changed_during_read')
        fraction = POLICY['learning_fraction' if self.learning else 'lookup_fraction']
        if np.any(self.counts < int(np.ceil(self.part.dimension * fraction))):
            self.fail('insufficient_payload')
        audit = {'status':'held' if self.failure else 'ready', 'reason':self.failure,
                 'ticks_received':self.next_tick, 'expected_ticks':self.length,
                 'data_counts':self.counts.tolist(), 'head':self.head_audit, 'tail':self.tail_audit,
                 'learning_read':self.learning, 'eligible_for_decision':not bool(self.failure)}
        if self.failure:
            return None, audit
        scores = self.acc.real / self.counts[:,None]
        if not np.isfinite(scores).all():
            return None, dict(audit, status='held', reason='nonfinite_scores', eligible_for_decision=False)
        return scores, audit


def read_scores(part, key, nonce, learning=False, port_factory=ExactPort, chunk=1):
    require(type(chunk) is int and 1 <= chunk <= 1024, 'chunk_range')
    window = ReadWindow(part, key, nonce, learning)
    batch = []
    for event in port_factory(part, key, nonce):
        batch.append(event)
        if len(batch) == chunk:
            window.push_many(batch)
            batch.clear()
    window.push_many(batch)
    return window.finish()
