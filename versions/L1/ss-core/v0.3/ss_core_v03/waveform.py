"""One numeric, causal correlation receiver for language and correction reads.

The receiver owns public reference codes, not learned source coefficients. Only
the simulated DAC port sees the source. A valid tail is required before scores
can be used. No source-wide dot product or cached recalled answer is used.
"""
import hashlib
import numpy as np
from plm_l1_v09.component.algebra import require
from plm_l1_v09.component.banked import FreshBook

PILOT = 16

def fingerprint(a):
    return hashlib.sha256(np.asarray(a, dtype='<c16').tobytes()).hexdigest()

class ArrayPort:
    def __init__(self, source, pilots, tag):
        self.source, self.pilots, self.tag = source, pilots, tag

    def __iter__(self):
        channels, width = self.source.shape
        mask = np.ones(channels, bool)
        for tick in range(width + 2*PILOT):
            if tick < PILOT:
                value = self.pilots[0, :, tick]
            elif tick < width + PILOT:
                value = self.source[:, tick-PILOT]
            else:
                value = self.pilots[1, :, tick-width-PILOT]
            yield tick, value.copy(), mask.copy()

class Receiver:
    def __init__(self, basis, demod, pilots, fraction=1.0):
        self.basis, self.demod, self.pilots = basis, demod, pilots
        self.channels, self.candidates, self.width = basis.shape
        require(self.channels > 0 and self.candidates > 0 and self.width > 0 and 0 < fraction <= 1, 'receiver_dimensions_fraction')
        require(demod.shape == (self.channels, self.width), 'demod_shape')
        self.fraction = fraction
        self.acc = np.zeros((self.channels, self.candidates), complex)
        self.counts = np.zeros(self.channels, int)
        self.p = np.zeros_like(pilots)
        self.masks = np.zeros(pilots.shape, bool)
        self.rotation = np.ones(self.channels, complex)
        self.next_tick = 0
        self.failure = None
        self.closed = False
        self.received_hash = hashlib.sha256()

    def fail(self, reason):
        self.failure = self.failure or reason

    def pilot_check(self, side):
        m = self.masks[side]
        count = m.sum(axis=1)
        z = (self.p[side]*self.pilots[side].conj()*m).sum(axis=1)
        power = (abs(self.p[side])**2*m).sum(axis=1)
        if side == 0:
            self.rotation = np.exp(-1j*np.angle(z))
        coherence = abs(z)/np.sqrt(np.maximum(power*count, 1e-30))
        residual = np.sqrt((abs(self.p[side]*self.rotation[:, None]-self.pilots[side])**2*m).sum(axis=1)/np.maximum(count, 1))
        if not (np.all(count >= 12) and np.all(coherence >= .95) and np.all(residual <= .10)):
            self.fail('head_pilot' if side == 0 else 'tail_pilot')

    def push(self, tick, sample, observed):
        if self.closed:
            self.fail('read_after_close')
            return
        if self.failure:
            return
        if type(tick) is not int or tick != self.next_tick or tick >= self.width+2*PILOT:
            self.fail('tick_order_or_length')
            return
        y, mask = np.asarray(sample), np.asarray(observed)
        if y.shape != (self.channels,) or y.dtype.kind not in 'fc' or mask.shape != y.shape or mask.dtype != bool:
            self.fail('sample_contract')
            return
        if not np.isfinite(y).all() or np.any(y[~mask] != 0):
            self.fail('sample_nonfinite_or_missing_nonzero')
            return
        self.next_tick += 1
        self.received_hash.update(y.astype('<c16').tobytes())
        self.received_hash.update(mask.tobytes())
        if tick < PILOT:
            self.p[0, :, tick], self.masks[0, :, tick] = y, mask
            if tick == PILOT-1:
                self.pilot_check(0)
        elif tick < PILOT+self.width:
            j = tick-PILOT
            # The only learned-source/reference multiplication in the receiver.
            self.acc += self.basis[:, :, j].conj()*(y*self.rotation*self.demod[:, j])[:, None]
            self.counts += mask
        else:
            j = tick-PILOT-self.width
            self.p[1, :, j], self.masks[1, :, j] = y, mask
            if j == PILOT-1:
                self.pilot_check(1)

    def peek(self):
        return {'eligible_for_decision': False, 'ticks': self.next_tick, 'reason': self.failure}

    def finish(self):
        if self.closed:
            self.fail('already_closed')
        self.closed = True
        if self.next_tick != self.width+2*PILOT:
            self.fail('incomplete_window')
        if np.any(self.counts < np.ceil(self.width*self.fraction)):
            self.fail('insufficient_payload')
        audit = {'status': 'held' if self.failure else 'ready', 'reason': self.failure,
                 'ticks': self.next_tick, 'expected_ticks': self.width+2*PILOT,
                 'channels': self.channels, 'candidates': self.candidates,
                 'counts': self.counts.tolist(), 'received_sha256': self.received_hash.hexdigest(),
                 'eligible_for_decision': not bool(self.failure)}
        if not np.isfinite(self.acc).all():
            self.fail('nonfinite_accumulator')
            audit.update(status='held', reason=self.failure, eligible_for_decision=False)
        return (None if self.failure else self.acc.real/np.maximum(self.counts[:, None], 1)), audit

class Engine:
    def __init__(self, port_factory=ArrayPort):
        self.port_factory = port_factory
        self.trace = []

    def correlate(self, source, basis, tag, demod=None, fraction=1.0):
        source, basis = np.asarray(source), np.asarray(basis)
        if source.ndim == 1:
            source = source[None, :]
        if basis.ndim == 2:
            basis = basis[None, :, :]
        require(source.ndim == 2 and basis.ndim == 3 and source.shape == (basis.shape[0], basis.shape[2]), 'wave_shape')
        require(np.isfinite(source).all() and np.isfinite(basis).all(), 'wave_finite')
        if demod is None:
            demod = np.ones_like(source)
        demod = np.asarray(demod).reshape(source.shape)
        require(np.isfinite(demod).all(), 'demod_finite')
        nonce = len(self.trace)
        book = FreshBook(PILOT, 'language-wave03')
        pilots = np.array([[book.code('pilot', [tag, nonce, side, c]) for c in range(source.shape[0])] for side in (0, 1)])
        before = fingerprint(source)
        receiver = Receiver(basis, demod, pilots, fraction)
        for event in self.port_factory(source, pilots, tag):
            receiver.push(*event)
        if fingerprint(source) != before:
            receiver.fail('source_changed')
        scores, audit = receiver.finish()
        self.trace.append({'id': nonce, 'tag': tag, 'source_sha256': before, **audit})
        require(scores is not None, 'wave_hold:'+tag+':'+str(audit['reason']))
        return scores

    def stats(self, start=0):
        rows = self.trace[start:]
        return {'windows': len(rows), 'ticks': sum(r['ticks'] for r in rows),
                'candidate_channel_tick_products': sum(sum(r['counts'])*r['candidates'] for r in rows),
                'held_windows': sum(r['status'] != 'ready' for r in rows),
                'families': sorted({r['tag'].split('/')[0] for r in rows})}
