"""Read inherited learned blocks through waveform acquisition; no answer cache."""
import numpy as np
from plm_l1_v09.component.banked import (META_BYTES, FreshBook, key_code, value_code,
                                        route, bank_seed)
from plm_l1_v09.component.algebra import require
from plm_l1_v09.thresholds import MIN_SCORE, MIN_MARGIN, MIN_PROOF

class WaveMemory:
    def __init__(self, original, engine, name):
        self.blocks, self.engine, self.name = original.blocks, engine, name
        self.references = {}  # public reference codes only; never answers/scores

    def recall(self, context):
        audits = []
        for blockno, block in enumerate(self.blocks):
            m = block.meta()
            require(all(f in context for f in m['mask']), 'missing_query_field')
            key = {f: context[f] for f in m['mask']}
            bank = route(key, m['banks'])
            dv, dp = m['value_width'], m['proof_width']
            start = bank*(dv+dp)
            weights = np.frombuffer(block.blob, dtype='<c16', offset=META_BYTES)
            ident = (blockno, bank)
            if ident not in self.references:
                book = FreshBook(dv, bank_seed(m['seed'], bank, m['banks']))
                basis = np.array([value_code(book, c) for c in m['candidates']])
                self.references[ident] = (book, basis)
            book, basis = self.references[ident]
            scores = self.engine.correlate(weights[start:start+dv], basis,
                                           self.name+'/value/'+str(blockno), key_code(book, key))[0]
            order = np.argsort(-scores, kind='stable')
            top = float(scores[order[0]])
            runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
            candidate = m['candidates'][order[0]]
            good = top >= MIN_SCORE and top-runner >= MIN_MARGIN
            evidence = None
            if dp:
                proof = FreshBook(dp, bank_seed(m['seed'], bank, m['banks'])+'/pair-evidence')
                ref = proof.code('key_value_pair', [key, candidate])[None, :]
                evidence = float(self.engine.correlate(weights[start+dv:start+dv+dp], ref,
                                                        self.name+'/proof/'+str(blockno))[0, 0])
                if m['mode'] in (2, 3):
                    good = good and evidence >= MIN_PROOF
            audits.append({'mask': m['mask'], 'bank': bank, 'bank_load': m['counts'][bank], 'banks': m['banks'],
                           'value': candidate if good else None, 'score': round(top, 8), 'margin': round(top-runner, 8),
                           'evidence': None if evidence is None else round(evidence, 8), 'evidence_required': m['mode'] in (2, 3)})
        accepted = {a['value'] for a in audits if a['value'] is not None}
        return {'value': next(iter(accepted)) if len(accepted) == 1 else None,
                'reason': 'recalled' if len(accepted) == 1 else 'weak_unregistered_or_conflicting_projection', 'projections': audits}

    def clear_cache(self):
        self.references.clear()
