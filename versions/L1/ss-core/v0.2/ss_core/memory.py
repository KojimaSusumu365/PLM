"""Read-only adapter; preserves the inherited SS decision policy and storage format."""
import numpy as np
from plm_l1_v09.component.algebra import require
from ss_retention.memory import POLICY
from .clock import ExactPort, read_scores


def decision(part, key, role, scores):
    indexes = [i for i,x in enumerate(part.labels) if x[0] == role]
    require(len(indexes) >= 2, 'query_domain')
    s = scores[:,indexes]
    means = s.mean(axis=0)
    order = np.argsort(-means, kind='stable')
    best = int(order[0])
    top = float(means[best])
    gap = top - max(0., float(means[order[1]]))
    votes = int(np.sum(np.argmax(s, axis=1) == best))
    accepted = (top >= POLICY['score'] and int(np.sum(means >= POLICY['score'])) == 1
                and gap >= POLICY['margin'] and votes >= POLICY['minimum_channel_votes'])
    return {'value':part.labels[indexes[best]][1] if accepted else None,
            'top_value':part.labels[indexes[best]][1],
            'scores':[[round(float(v),8) for v in row] for row in s],
            'mean_scores':[round(float(v),8) for v in means], 'score':round(top,8),
            'margin':round(gap,8), 'votes':votes, 'registered':key in part.registry,
            'accepted_raw':bool(accepted)}


class WaveCorrectionView:
    def __init__(self, memory, port_factory=ExactPort, chunk=1):
        require(memory.method == 'split_pair', 'split_pair_only')
        self.memory, self.port_factory, self.chunk = memory, port_factory, chunk
        self.traces = []

    def recall(self, key, role):
        raw, audits = {}, {}
        for name, part in self.memory.parts.items():
            scores, audit = read_scores(part, key, 'lookup/'+name, False, self.port_factory, self.chunk)
            audits[name] = audit
            if scores is not None:
                raw[name] = decision(part, key, role, scores)
        self.traces.append({'key':key, 'role':role, 'windows':audits})
        if any(a['status'] != 'ready' for a in audits.values()):
            return {'status':'waveform_hold', 'value':None, 'raw':raw, 'windows':audits}
        registered = [name for name,p in self.memory.parts.items() if key in p.registry]
        if not registered:
            return {'status':'unregistered', 'value':None, 'raw':raw}
        selected = 'protected' if 'protected' in registered else 'main'
        r = raw[selected]
        if r['value'] is None:
            return {'status':'weak_support', 'value':None, 'raw':raw}
        if selected == 'protected' and raw['main']['value'] is not None and raw['main']['value'] != r['value']:
            return {'status':'memory_disagreement', 'value':None, 'raw':raw}
        return {'status':'supported', 'value':r['value'], 'selected':selected, 'raw':raw}

    def registered(self, key):
        return self.memory.registered(key)


class WaveRevisionView:
    def __init__(self, memory, port_factory=ExactPort, chunk=1):
        require(memory.method == 'versioned_pair', 'versioned_pair_only')
        self.memory = memory
        self.ss = WaveCorrectionView(memory.ss, port_factory, chunk)
        self.roots, self.policy = memory.roots, memory.policy
        self.method, self.seed = memory.method, memory.seed

    @property
    def fingerprint(self):
        return self.memory.fingerprint

    def cost(self):
        return self.memory.cost()
