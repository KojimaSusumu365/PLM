"""Evaluator-only faults. Receiver is given samples/masks, never these parameters."""
import hashlib
import numpy as np
from ss_core.clock import ExactPort, PILOT

CONDITIONS = ('exact','phase','drop25','drop50','tail_drift','pilot_missing','truncate','reorder','payload_noise')

def factory(condition='exact', seed=0):
    assert condition in CONDITIONS
    def port(part, key, nonce):
        number = int.from_bytes(hashlib.sha256((str(seed)+'/'+part.seed+'/'+key+'/'+nonce).encode()).digest()[:8], 'little')
        rng = np.random.default_rng(number)
        source = ExactPort(part,key,nonce)
        for tick, y, mask in source:
            data = PILOT <= tick < PILOT+part.dimension
            if condition == 'phase':
                y *= np.exp(1j*np.array([.73,-.91,1.7,-2.1]))
            elif condition in ('drop25','drop50') and data:
                period = 4 if condition=='drop25' else 2
                mask[(tick-PILOT)%period == np.arange(4)%period] = False
                y[~mask] = 0
            elif condition == 'tail_drift':
                y *= np.exp(1j*.5*max(0,tick-PILOT)/part.dimension)
            elif condition == 'pilot_missing' and not data:
                mask[:] = False
                y[:] = 0
            elif condition == 'truncate' and tick >= source.length-8:
                return
            elif condition == 'reorder' and tick in (PILOT+5,PILOT+6):
                tick += 1 if tick==PILOT+5 else -1
            elif condition == 'payload_noise' and data:
                y += 16*(rng.standard_normal(4)+1j*rng.standard_normal(4))
            yield tick, y, mask
    return port
