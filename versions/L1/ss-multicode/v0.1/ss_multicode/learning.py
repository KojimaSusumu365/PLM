"""External-teacher transactions. No replay buffer or self-training."""
import copy
import json
from pathlib import Path
import numpy as np
from .algebra import canonical, digest, require
from .model import Model, SPECS, LABELS


class Learner:
    def __init__(self, model, step=0, history=None):
        require(type(step) is int and step >= 0, 'step')
        self.model = model; self.step = step; self.history = history or digest(['empty-multicode-history'])
        require(type(self.history) is str and len(self.history) == 64, 'history')
        self.refresh()

    def refresh(self):
        self.state = {'schema': 'plm-ss-multicode-learner-01', 'step': self.step, 'history': self.history,
                      'model_fingerprint': self.model.fingerprint, 'learning_rate': .5, 'eligible_for_inference': False}
        self.fingerprint = digest(self.state)

    def question(self, context):
        self.model.validate(context)
        req = {'schema': 'plm-ss-multicode-request-01', 'state_fingerprint': self.fingerprint, 'context': copy.deepcopy(context)}
        req['request_id'] = digest(req)
        return {'request': req, 'prediction': self.model.predict([context])[0]}

    def answer(self, req, feedback):
        require(type(req) is dict and set(req) == {'schema', 'state_fingerprint', 'context', 'request_id'}, 'request_schema')
        require(req['schema'] == 'plm-ss-multicode-request-01' and req['state_fingerprint'] == self.fingerprint, 'stale_request')
        require(req == self.question(req['context'])['request'], 'tampered_request')
        require(type(feedback) is dict and set(feedback) == {'schema', 'request_id', 'source', 'label'}, 'feedback_schema')
        require(feedback['schema'] == 'plm-ss-multicode-feedback-01' and feedback['request_id'] == req['request_id'], 'feedback_request')
        require(feedback['source'] == 'external_teacher', 'prediction_is_not_teacher')
        require(type(feedback['label']) is str and feedback['label'] in LABELS, 'known_teacher_label_required')
        old = self.model; c = req['context']; y = feedback['label']
        model = Model(old.architecture, old.seed, old.readers, old.checker, old.entries, old.acceptance)
        model.books = old.books; model.check_book = old.check_book  # immutable symbol definitions; cache is not learning
        target = np.array([int(label == y) for label in LABELS], dtype=float)
        if old.architecture == 'exact':
            model.entries[canonical(c)] = y
        else:
            b, z = model.vectors([c]); b = b[0]; z = z[0]
            d = model.readers.shape[2]
            s = np.einsum('kd,kyd->ky', b, model.readers.conj()).real / d
            err = target[None, :] - (s.mean(axis=0, keepdims=True) if SPECS[old.architecture][2] else s)
            model.readers += .5 * err[:, :, None] * b[:, None, :]
            if len(model.checker):
                cs = (z @ model.checker.conj()).real / len(model.checker)
                # One simultaneous residual correction for four candidate pairs, from this one teacher.
                model.checker += .5 * ((target - cs)[:, None] * z).sum(axis=0)
        model.refresh()
        return Learner(model, self.step + 1, digest([self.history, req['request_id'], feedback]))

    def storage(self):
        k, d, shared, cd = SPECS[self.model.architecture]
        return self.model.storage() | {'teacher_presentations': self.step,
            'reader_vector_updates': self.step * (k if d else 0),
            'pair_vector_updates': self.step * (1 if cd else 0),
            'reader_coefficient_update_elements': self.step * k * 4 * d,
            'pair_correlation_elements': self.step * 4 * cd,
            'learner_utf8_bytes': len(canonical(self.state).encode('utf-8'))}

    def save(self, directory):
        p = Path(directory); p.mkdir(parents=True, exist_ok=False); self.model.save(p / 'model')
        with (p / 'learner.json').open('x', encoding='utf-8') as f:
            json.dump({'state': self.state, 'fingerprint': self.fingerprint}, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, directory):
        p = Path(directory); require({f.name for f in p.iterdir()} == {'model', 'learner.json'}, 'learner_inventory')
        obj = json.loads((p / 'learner.json').read_text(encoding='utf-8')); s = obj['state']
        model = Model.load(p / 'model'); learner = cls(model, s['step'], s['history'])
        require(learner.state == s and learner.fingerprint == obj['fingerprint'], 'learner_fingerprint')
        return learner


def teacher(request, label):
    return {'schema': 'plm-ss-multicode-feedback-01', 'request_id': request['request_id'],
            'source': 'external_teacher', 'label': label}
