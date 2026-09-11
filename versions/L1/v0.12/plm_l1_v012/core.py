"""A veto-only semantic sufficiency guard built from learned memories.

Completion enumeration is ordinary control over the *training* vocabulary.
It is not an evaluator oracle, logical omniscience, or an SS-only controller.
"""
import hashlib
import itertools
import json
import math
from pathlib import Path
import numpy as np
from plm_l1_v011.algebra import canonical, digest, require
from plm_l1_v011.core import Model, exact_scores, winner
from .evidence import EvidenceMemory, SUPPORT_THRESHOLD

POLICIES = ('baseline', 'observed_only', 'consensus_only', 'completion')
MAX_COMPLETIONS = 256


class GuardedModel:
    def __init__(self, base, evidence, training, max_completions=MAX_COMPLETIONS):
        require(type(max_completions) is int and 1 <= max_completions <= 4096, 'invalid_completion_limit')
        require(len(evidence) == len(base.members), 'witness_member_mismatch')
        self.base = base
        self.evidence = evidence
        self.training = training
        self.max_completions = max_completions
        self.refresh()

    def refresh(self):
        self.meta = {'schema': 'plm-sufficiency-v012', 'base_fingerprint': self.base.fingerprint,
                     'training': self.training, 'max_completions': self.max_completions,
                     'evidence': [e.metadata() for e in self.evidence],
                     'eligible_for_inference': False,
                     'scope': 'Learned masks and finite training vocabulary; no truth guarantee for unlearned dependencies.'}
        self.fingerprint = digest([self.meta, [hashlib.sha256(e.weights.astype('<c16').tobytes()).hexdigest() for e in self.evidence]])

    def _member_prediction(self, index, context):
        m = self.base.members[index]
        if self.base.config['backend'] == 'ss':
            q, _ = self.base.books[index].vector(context, m['mask'], self.base.config['representation'])
            scores = (m['weights'].conj() @ q).real / m['dimension']
        else:
            scores = exact_scores([context], m['mask'], self.base.config['representation'],
                                  m['counts'], m['class_counts'])[0]
        value, margin = winner(scores, self.base.config['labels'])
        return (value if margin >= self.base.threshold else None), margin

    def predict(self, context, *, policy='completion'):
        require(policy in POLICIES, 'invalid_guard_policy')
        self.base.validate_context(context)
        before = self.base.predict(context)
        result = {'status': before['status'], 'value': before['value'], 'reason': before['reason'],
                  'policy': policy, 'baseline_value': before['value'], 'baseline_reason': before['reason'],
                  'confidence': before['confidence'], 'evidence': [], 'completion_count': 0,
                  'model_fingerprint': self.fingerprint, 'eligible_for_inference': False}

        def veto(reason):
            result.update(status='abstain', value=None, reason=reason)
            return result

        if policy == 'baseline' or before['value'] is None:
            return result
        missing = [[f for f in m['mask'] if f not in context] for m in self.base.members]
        if policy == 'observed_only':
            return veto('missing_selected_features') if any(missing) else result
        counts = [math.prod(len(self.base.config['vocabulary'][f]) for f in fs) for fs in missing]
        if sum(counts) > self.max_completions:
            return veto('completion_budget_exceeded')
        expected = before['value']
        failure = False
        for i, (m, absent, count, memory) in enumerate(zip(self.base.members, missing, counts, self.evidence)):
            audit = {'member': i, 'completions': count, 'answers': [], 'prediction_abstentions': 0,
                     'prediction_disagreements': 0, 'missing_witnesses': 0, 'conflicting_witnesses': 0,
                     'minimum_expected_support': None, 'minimum_prediction_margin': None}
            answers = set()
            supports = []
            margins = []
            for values in itertools.product(*(self.base.config['vocabulary'][f] for f in absent)):
                completed = {f: context[f] for f in m['mask'] if f in context}
                completed.update(zip(absent, values))
                answer, margin = self._member_prediction(i, completed)
                margins.append(margin)
                if answer is None:
                    audit['prediction_abstentions'] += 1
                else:
                    answers.add(answer)
                    audit['prediction_disagreements'] += int(answer != expected)
                if policy == 'completion':
                    witness = memory.assess(completed, expected)
                    supports.append(witness['scores'][self.base.config['labels'].index(expected)])
                    if expected not in witness['hits']:
                        audit['missing_witnesses'] += 1
                    if any(y != expected for y in witness['hits']):
                        audit['conflicting_witnesses'] += 1
            audit['answers'] = sorted(answers)
            audit['minimum_prediction_margin'] = min(margins)
            audit['minimum_expected_support'] = min(supports) if supports else None
            failure |= any(audit[k] for k in ('prediction_abstentions', 'prediction_disagreements', 'missing_witnesses', 'conflicting_witnesses'))
            result['evidence'].append(audit)
            result['completion_count'] += count
        return veto('insufficient_learned_evidence') if failure else result

    def storage(self):
        return {'base': self.base.storage(),
                'witness_complex_weight_bytes': sum(e.weights.nbytes for e in self.evidence),
                'witness_integer_entries': sum(sum(len(v) for v in e.entries.values()) for e in self.evidence),
                'witness_warm_codebook_bytes': sum(v.nbytes for e in self.evidence for v in e.book.cache.values()),
                'guard_metadata_utf8_bytes': len(canonical(self.meta).encode('utf-8')),
                'scope': 'Owned arrays and serialized metadata only; not total RSS or energy.'}

    def save(self, directory):
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=False)
        self.base.save(p / 'base')
        with (p / 'guard.json').open('x', encoding='utf-8') as f:
            f.write(json.dumps({'metadata': self.meta, 'fingerprint': self.fingerprint}, ensure_ascii=False, indent=2) + '\n')
        np.savez(p / 'witnesses.npz', **{f'member_{i}': e.weights for i, e in enumerate(self.evidence)})

    @classmethod
    def load(cls, directory):
        p = Path(directory)
        require({x.name for x in p.iterdir()} == {'base', 'guard.json', 'witnesses.npz'}, 'invalid_guard_inventory')
        obj = json.loads((p / 'guard.json').read_text(encoding='utf-8'))
        require(set(obj) == {'metadata', 'fingerprint'}, 'invalid_guard_envelope')
        meta = obj['metadata']
        require(meta['schema'] == 'plm-sufficiency-v012' and meta['eligible_for_inference'] is False, 'invalid_guard_contract')
        base = Model.load(p / 'base')
        require(base.fingerprint == meta['base_fingerprint'], 'guard_base_mismatch')
        require(len(meta['evidence']) == len(base.members), 'witness_member_mismatch')
        memories = []
        with np.load(p / 'witnesses.npz', allow_pickle=False) as arrays:
            require(set(arrays.files) == {f'member_{i}' for i in range(len(base.members))}, 'invalid_witness_inventory')
            for i, (em, member) in enumerate(zip(meta['evidence'], base.members)):
                require(em['fields'] == member['mask'] and em['labels'] == base.config['labels'] and
                        em['backend'] == base.config['backend'] and em['dimension'] == member['dimension'] and
                        em['threshold'] == SUPPORT_THRESHOLD, 'witness_config_mismatch')
                w = arrays[f'member_{i}']
                shape = (len(em['labels']), em['dimension']) if em['backend'] == 'ss' else (0, 0)
                require(w.dtype == np.complex128 and w.shape == shape and np.isfinite(w).all(), 'invalid_witness_weights')
                require(type(em['entries']) is dict and (em['backend'] != 'ss' or not em['entries']), 'invalid_witness_table')
                memories.append(EvidenceMemory(em['fields'], em['labels'], em['dimension'], em['seed'], em['backend'], w.copy(), em['entries'], em['key_counts']))
        model = cls(base, memories, meta['training'], meta['max_completions'])
        require(model.meta == meta and model.fingerprint == obj['fingerprint'], 'guard_fingerprint_mismatch')
        return model
