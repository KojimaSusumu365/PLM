"""Teacher-facing bookkeeping, separate from prediction-only runtime."""
import copy
import json
from pathlib import Path
from .algebra import canonical, digest, require
from .core import Model
from .training import fit


class Session:
    def __init__(self, rows, pool, settings, model=None, receipts=None):
        self.rows = copy.deepcopy(rows)
        self.pool = copy.deepcopy(pool)
        self.settings = copy.deepcopy(settings)
        self.model = fit(self.rows, **self.settings)[0] if model is None else model
        require(digest(self.rows) == self.model.training['digest'], 'session_teacher_model_mismatch')
        # Validates unlabeled schema even when hypothesis family is exhausted.
        self.model.rank_pool(self.pool, 'random')
        seen = {canonical(r['context']) for r in self.rows}
        require(not any(canonical(p['context']) in seen for p in self.pool), 'pool_overlaps_observed_teachers')
        self.receipts = copy.deepcopy(receipts or [])

    def choose(self, strategy='active', seed='acquisition-0'):
        return self.model.select(self.pool, strategy, seed)

    def answer(self, request, label):
        require(type(request) is dict and set(request) == {'schema', 'model_fingerprint', 'id', 'context', 'strategy', 'seed', 'diagnostics', 'eligible_for_inference'}, 'invalid_teacher_request')
        require(request['schema'] == 'plm-teacher-request-v013' and request['eligible_for_inference'] is False and request['model_fingerprint'] == self.model.fingerprint, 'stale_teacher_request')
        require(type(label) is str and label in self.model.config['labels'], 'new_label_requires_scope_review')
        expected = self.choose(request['strategy'], request['seed'])
        require(request == expected, 'request_does_not_match_selection')
        item = next((p for p in self.pool if p['id'] == request['id']), None)
        require(item is not None and item['context'] == request['context'], 'teacher_request_not_in_pool')
        rows = self.rows + [{'context': item['context'], 'label': label}]
        pool = [p for p in self.pool if p['id'] != item['id']]
        receipt = {'id': item['id'], 'context': item['context'], 'label': label, 'request_fingerprint': digest(request),
                   'prior_model_fingerprint': self.model.fingerprint}
        return Session(rows, pool, self.settings, receipts=self.receipts + [receipt])

    def save(self, directory):
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=False)
        self.model.save(p / 'model')
        state = {'schema': 'plm-teaching-session-v013', 'rows': self.rows, 'pool': self.pool, 'settings': self.settings,
                 'receipts': self.receipts, 'model_fingerprint': self.model.fingerprint}
        with (p / 'session.json').open('x', encoding='utf-8') as f:
            f.write(json.dumps({'state': state, 'fingerprint': digest(state)}, ensure_ascii=False, indent=2) + '\n')

    @classmethod
    def load(cls, directory):
        p = Path(directory)
        require({x.name for x in p.iterdir()} == {'session.json', 'model'}, 'invalid_session_inventory')
        obj = json.loads((p / 'session.json').read_text(encoding='utf-8'))
        require(set(obj) == {'state', 'fingerprint'} and digest(obj['state']) == obj['fingerprint'], 'session_fingerprint_mismatch')
        state = obj['state']
        require(state['schema'] == 'plm-teaching-session-v013', 'invalid_session_schema')
        model = Model.load(p / 'model')
        require(state['model_fingerprint'] == model.fingerprint, 'session_model_mismatch')
        return cls(state['rows'], state['pool'], state['settings'], model, state['receipts'])
