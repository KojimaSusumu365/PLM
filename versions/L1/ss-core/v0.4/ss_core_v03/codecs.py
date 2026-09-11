"""Waveform cleanup of semantic packets. Symbolic schemas remain explicit."""
import itertools
import math
import numpy as np
from plm_l1_v09.component.algebra import require
from plm_l1_v09.component.lexicon import ROLES
from plm_l1_v09.thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MAX_RESIDUAL
from ss_document.codec import DocumentCodec
from ss_document.contract import IDS, normalize
from ss_partial.codec import PartialCodec
from ss_partial.contract import STATES, inventory, normalize as partial_normalize

class BasisScan:
    def __init__(self, entries, engine, tag):
        self.slices = {}
        arrays, offset = [], 0
        for key, basis in entries:
            basis = np.atleast_2d(basis)
            self.slices[key] = slice(offset, offset+len(basis))
            arrays.append(basis)
            offset += len(basis)
        self.basis = np.concatenate(arrays)
        self.engine, self.tag = engine, tag

    def read(self, vector):
        scores = self.engine.correlate(vector, self.basis, self.tag)[0]
        return {key: scores[sl] for key, sl in self.slices.items()}

def choose(scores, reason):
    order = np.argsort(-scores, kind='stable')
    top = float(scores[order[0]])
    runner = max(0., float(scores[order[1]])) if len(order)>1 else 0.
    require(top >= MIN_SCORE and top-runner >= MIN_MARGIN, reason)
    return int(order[0]), {'score': round(top, 8), 'margin': round(top-runner, 8)}

def residual(vector, clean, reason):
    # Numerical integrity reduction, not a hidden semantic decoder.
    value = float(np.linalg.norm(vector-clean)/np.linalg.norm(clean))
    require(value <= MAX_RESIDUAL, reason)
    return round(value, 8)

class WaveDocumentCodec(DocumentCodec):
    def __init__(self, original, engine):
        self.__dict__.update(original.__dict__)
        entries = [('count', self.counts)]
        entries += [('presence/'+str(i), a) for i, a in enumerate(self.presence)]
        entries += [('slot/'+str(i)+'/'+r, a) for i, event in enumerate(self.events) for r, a in event.items()]
        entries += [('time/'+str(pair), a) for pair, a in self.relations.items()]
        entries += [('order/'+str(n), a) for n, a in self.order_codes.items()]
        self.scan = BasisScan(entries, engine, 'document_packet')

    def recover(self, vector):
        require(isinstance(vector, np.ndarray) and vector.shape == (self.dimension,) and np.isfinite(vector).all(), 'finite_document_vector')
        s = self.scan.read(vector*math.sqrt(3.))
        ci, ca = choose(s['count'], 'ambiguous_event_count')
        n, events, audits = ci+2, [], []
        for i in range(n):
            strength = float(s['presence/'+str(i)][0])
            require(strength >= MIN_PRESENCE, 'missing_event_presence')
            event, details = {'id': IDS[i]}, {}
            for role in ROLES:
                j, details[role] = choose(s['slot/'+str(i)+'/'+role], 'ambiguous_event_slot')
                event[role] = self.candidates[role][j]
            events.append(event)
            audits.append({'id': IDS[i], 'presence': round(strength, 8), 'slots': details})
        relations, ra = [], []
        for pair in itertools.combinations(IDS[:n], 2):
            j, detail = choose(s['time/'+str(pair)], 'ambiguous_time_direction')
            relations.append(self.relation_values[pair][j])
            ra.append(detail)
        oi, oa = choose(s['order/'+str(n)], 'ambiguous_presentation')
        meaning = normalize({'events': events, 'relations': relations, 'presentation': self.orders[n][oi]}, self.candidates)
        return {'meaning': meaning, 'residual': residual(vector, self.encode(meaning), 'document_residual_excessive'),
                'count_audit': ca, 'event_audit': audits, 'relation_audit': ra, 'order_audit': oa}

class WavePartialCodec(PartialCodec):
    def __init__(self, original, engine):
        self.__dict__.update(original.__dict__)
        entries = [('count', self.base.counts)]
        entries += [('presence/'+str(i), a) for i, a in enumerate(self.base.presence)]
        entries += [('order/'+str(n), a) for n, a in self.base.order_codes.items()]
        for key in self.choices:
            entries.extend([('state/'+key, self.states[key]), ('arity/'+key, self.arities[key]), ('value/'+key, self.values[key])])
        self.scan = BasisScan(entries, engine, 'partial_packet')

    def recover(self, vector):
        require(vector.shape == (self.dimension,) and np.isfinite(vector).all(), 'partial_vector')
        s = self.scan.read(vector*math.sqrt(3.))
        ci, _ = choose(s['count'], 'unreadable_count')
        n = ci+2
        for i in range(n):
            require(s['presence/'+str(i)][0] >= MIN_PRESENCE, 'unreadable_presence')
        oi, _ = choose(s['order/'+str(n)], 'unreadable_presentation')
        cells, evidence = {}, {}
        for key in inventory(n, self.candidates):
            si, sa = choose(s['state/'+key], 'unreadable_state:'+key)
            count, ca = choose(s['arity/'+key], 'unreadable_arity:'+key)
            scores = s['value/'+key]
            ranked = np.argsort(-scores, kind='stable')
            chosen = set(map(int, ranked[:count]))
            outside = max([0.]+[float(scores[j]) for j in ranked[count:]])
            if count:
                inside = float(scores[ranked[count-1]])
                require(inside >= MIN_SCORE and inside-outside >= MIN_MARGIN, 'unreadable_candidate_set:'+key)
            require(outside <= 1.-MIN_SCORE, 'unselected_candidate_evidence:'+key)
            cells[key] = {'state': STATES[si], 'candidates': [v for j, v in enumerate(self.choices[key]) if j in chosen]}
            evidence[key] = {'state': sa, 'arity': ca, 'scores': [round(float(v), 8) for v in scores]}
        observation = partial_normalize({'count': n, 'presentation': self.base.orders[n][oi], 'cells': cells}, self.candidates)
        return {'observation': observation, 'residual': residual(vector, self.encode(observation), 'partial_residual_excessive'), 'evidence': evidence}
