"""SS state and candidate-set carrier; fixed correlated codes, not learned uncertainty."""
import math
import numpy as np
from plm_l1_v09.component.banked import FreshBook
from plm_l1_v09.component.algebra import require
from plm_l1_v09.thresholds import MIN_SCORE, MIN_MARGIN, MAX_RESIDUAL, MIN_PRESENCE
from ss_document.codec import DocumentCodec
from ss_document.contract import IDS
from .contract import STATES, inventory, normalize, event_address, time_address


class PartialCodec:
    def __init__(self, candidates, dimension=8192, seed='partial-code-0', mode='bound'):
        require(mode in ('bound', 'unbound_events', 'drop_state'), 'partial_mode')
        self.dimension, self.seed, self.mode = dimension, seed, mode
        self.base = DocumentCodec(candidates, dimension, seed, 'unbound_events' if mode == 'unbound_events' else 'bound')
        self.candidates = self.base.candidates
        self.choices = inventory(3, candidates)
        self.values = {event_address(i, r): basis for i, slots in zip(IDS, self.base.events) for r, basis in slots.items()}
        self.values.update({time_address(pair): basis for pair, basis in self.base.relations.items()})
        b = FreshBook(dimension, 'partial-observation-v02/' + seed)
        self.states, self.arities = {}, {}
        for key, values in self.choices.items():
            address = b.code('address', key)
            self.states[key] = np.array([address * b.code('state', state) for state in STATES])
            self.arities[key] = np.array([address * b.code('arity', n) for n in range(len(values) + 1)])

    def cell_vector(self, target, value):
        v = self.arities[target][len(value['candidates'])].copy()
        if self.mode != 'drop_state':
            v += self.states[target][STATES.index(value['state'])]
        for item in value['candidates']:
            v += self.values[target][self.choices[target].index(item)]
        return v

    def encode(self, observation):
        o = normalize(observation, self.candidates)
        n = o['count']
        v = self.base.counts[n - 2].copy()
        for i in range(n):
            v += self.base.presence[i]
        v += self.base.order_codes[n][self.base.orders[n].index(o['presentation'])]
        for key, value in o['cells'].items():
            v += self.cell_vector(key, value)
        return v / math.sqrt(3.)

    def recover(self, vector):
        require(vector.shape == (self.dimension,) and np.isfinite(vector).all(), 'partial_vector')
        raw = vector * math.sqrt(3.)
        ci, _ = self.base.choose(self.base.counts, raw, 'unreadable_count')
        n = ci + 2
        for i in range(n):
            require(np.vdot(self.base.presence[i], raw).real / self.dimension >= MIN_PRESENCE, 'unreadable_presence')
        oi, _ = self.base.choose(self.base.order_codes[n], raw, 'unreadable_presentation')
        cells, evidence = {}, {}
        for key in inventory(n, self.candidates):
            si, sa = self.base.choose(self.states[key], raw, 'unreadable_state:' + key)
            count, ca = self.base.choose(self.arities[key], raw, 'unreadable_arity:' + key)
            scores = (self.values[key].conj() @ raw).real / self.dimension
            ranked = np.argsort(-scores, kind='stable')
            chosen = set(map(int, ranked[:count]))
            outside = max([0.] + [float(scores[j]) for j in ranked[count:]])
            if count:
                inside = float(scores[ranked[count - 1]])
                require(inside >= MIN_SCORE and inside - outside >= MIN_MARGIN, 'unreadable_candidate_set:' + key)
            else:
                require(outside <= 1. - MIN_SCORE, 'unexpected_candidate_evidence:' + key)
            # Unselected evidence must be weak: no silent dropping of an extra candidate.
            require(outside <= 1. - MIN_SCORE, 'unselected_candidate_evidence:' + key)
            values = [v for j, v in enumerate(self.choices[key]) if j in chosen]
            cells[key] = {'state': STATES[si], 'candidates': values}
            evidence[key] = {'state': sa, 'arity': ca, 'scores': [round(float(x), 8) for x in scores]}
        o = normalize({'count': n, 'presentation': self.base.orders[n][oi], 'cells': cells}, self.candidates)
        clean = self.encode(o)
        residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
        require(residual <= MAX_RESIDUAL, 'partial_residual_excessive')
        return {'observation': o, 'residual': round(residual, 8), 'evidence': evidence}

    def storage(self):
        extra = sum(a.nbytes for a in [*self.states.values(), *self.arities.values()])
        return self.base.storage() | {'partial_status_arity_basis_bytes': extra,
                                      'total_document_basis_bytes': self.base.storage()['document_basis_bytes'] + extra}
