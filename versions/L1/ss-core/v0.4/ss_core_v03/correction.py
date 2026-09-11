"""Existing correction memory is read with the same generalized chip receiver.

Version handling, pending flags, and v0.2 learning policies are not SS-ified here.
"""
from ss_core.memory import WaveCorrectionView, WaveRevisionView, decision
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate
from ss_core_v02.store import scope_id
from ss_core_v02.runtime import pending_result

class UnifiedCorrection(WaveCorrectionView):
    def __init__(self, memory, engine):
        super().__init__(memory)
        self.engine = engine

    def recall(self, key, role):
        raw, audits = {}, {}
        for name, part in self.memory.parts.items():
            try:
                scores = self.engine.correlate(part.weights, part.values, 'correction/'+name,
                                               part.context(key).conj(), fraction=.75)
                raw[name] = decision(part, key, role, scores)
                audits[name] = self.engine.trace[-1]
            except ValueError as e:
                return {'status': 'waveform_hold', 'value': None, 'reason': str(e), 'raw': raw}
        self.traces.append({'key': key, 'role': role, 'windows': audits})
        registered = [name for name, part in self.memory.parts.items() if key in part.registry]
        if not registered:
            return {'status': 'unregistered', 'value': None, 'raw': raw}
        selected = 'protected' if 'protected' in registered else 'main'
        r = raw[selected]
        if r['value'] is None:
            return {'status': 'weak_support', 'value': None, 'raw': raw}
        if selected == 'protected' and raw['main']['value'] is not None and raw['main']['value'] != r['value']:
            return {'status': 'memory_disagreement', 'value': None, 'raw': raw}
        return {'status': 'supported', 'value': r['value'], 'selected': selected, 'raw': raw}

def generate_saved(model, store, scope, packet, order='preserve', goals=None):
    if scope_id(scope) in store.pending:
        return pending_result()
    view = WaveRevisionView(store.memory)
    view.ss = UnifiedCorrection(store.memory.ss, model.engine)
    session = Session(model, view, scope, packet)
    result = generate(model, view, session, order=order, goals=goals)
    return {**result, 'memory_windows': view.ss.traces}
