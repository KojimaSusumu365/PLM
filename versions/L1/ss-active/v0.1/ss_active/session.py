"""Teacher transaction and label-free acquisition state. Shared SS core remains unchanged."""
import copy
import json
from pathlib import Path
from ss_multicode.algebra import digest, require
from ss_multicode.learning import Learner, teacher
from .selection import STRATEGIES, normalize_pool, select


class Session:
    def __init__(self, learner, pool, strategy='random', seed='acq-0', acquired=None, history=None, original_pool_digest=None):
        require(learner.model.architecture == 'concat512', 'shared_residual_model_required')
        require(strategy in STRATEGIES and type(seed) is str and 0 < len(seed) <= 80, 'strategy_seed')
        self.learner = learner; self.pool = normalize_pool(pool); self.strategy = strategy; self.seed = seed
        self.acquired = copy.deepcopy([] if acquired is None else acquired)
        require(type(self.acquired) is list and len(self.acquired) == len(set(self.acquired)) and
                all(type(k) is str and len(k) == 64 for k in self.acquired) and
                not set(self.acquired) & {r['id'] for r in self.pool} and len(self.pool) + len(self.acquired) <= 512, 'acquisition_ledger')
        self.history = history or digest(['empty-ss-active-history'])
        self.original_pool_digest = original_pool_digest or digest(self.pool)
        require(all(type(s) is str and len(s) == 64 for s in (self.history, self.original_pool_digest)), 'session_digests')
        self.refresh()

    def refresh(self):
        self.state = {'schema': 'plm-ss-active-session-01', 'learner_fingerprint': self.learner.fingerprint,
                      'pool': self.pool, 'strategy': self.strategy, 'seed': self.seed, 'acquired_ids': self.acquired,
                      'original_pool_digest': self.original_pool_digest, 'history': self.history,
                      'eligible_for_inference': False}
        self.fingerprint = digest(self.state)

    def ask(self):
        selection = select(self.learner.model, self.pool, self.strategy, self.seed, len(self.acquired))
        req = {'schema': 'plm-ss-active-request-01', 'session_fingerprint': self.fingerprint, 'selection': selection}
        req['request_id'] = digest(req)
        return req

    def answer(self, request, feedback):
        require(type(request) is dict and set(request) == {'schema', 'session_fingerprint', 'selection', 'request_id'}, 'request_schema')
        require(request['schema'] == 'plm-ss-active-request-01' and request['session_fingerprint'] == self.fingerprint, 'stale_request')
        require(request == self.ask(), 'tampered_or_unselected_request')
        require(type(feedback) is dict and set(feedback) == {'schema', 'request_id', 'source', 'label'}, 'feedback_schema')
        require(feedback['schema'] == 'plm-ss-active-feedback-01' and feedback['request_id'] == request['request_id'], 'feedback_request')
        require(feedback['source'] == 'external_teacher', 'prediction_is_not_teacher')
        require(type(feedback['label']) is str and feedback['label'] in list('0123'), 'known_label_required')
        item = request['selection']
        q = self.learner.question(item['context'])['request']
        learned = self.learner.answer(q, teacher(q, feedback['label']))
        pool = [r for r in self.pool if r['id'] != item['selected_id']]
        return Session(learned, pool, self.strategy, self.seed, self.acquired + [item['selected_id']],
                       digest([self.history, request['request_id'], feedback]), self.original_pool_digest)

    def save(self, directory):
        p = Path(directory); p.mkdir(parents=True, exist_ok=False); self.learner.save(p / 'learner')
        with (p / 'session.json').open('x', encoding='utf-8') as f:
            json.dump({'state': self.state, 'fingerprint': self.fingerprint}, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, directory):
        p = Path(directory); require({f.name for f in p.iterdir()} == {'learner', 'session.json'}, 'session_inventory')
        obj = json.loads((p / 'session.json').read_text(encoding='utf-8')); s = obj['state']
        session = cls(Learner.load(p / 'learner'), s['pool'], s['strategy'], s['seed'], s['acquired_ids'], s['history'], s['original_pool_digest'])
        require(session.state == s and session.fingerprint == obj['fingerprint'], 'session_fingerprint')
        return session


def feedback(request, label):
    return {'schema': 'plm-ss-active-feedback-01', 'request_id': request['request_id'], 'source': 'external_teacher', 'label': label}
