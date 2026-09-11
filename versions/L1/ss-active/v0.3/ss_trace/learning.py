"""Explicit external feedback; main and protected trace see the same acquisition teacher."""
import copy
import numpy as np
from ss_multicode.algebra import digest, require
from ss_multicode.model import Model, LABELS
from .runtime import context_id, choice, TRACE_D


def question(state, context, kind='acquisition'):
    Model.validate(context)
    require(kind in ('acquisition', 'background'), 'teacher_kind')
    require(not (kind == 'background' and context_id(context) in state.ledger), 'background_cannot_refresh_acquired')
    req = {'schema': 'plm-ss-active3-request', 'state_fingerprint': state.fingerprint,
           'context': copy.deepcopy(context), 'kind': kind}
    return req | {'request_id': digest(req)}


def answer(state, req, feedback):
    require(type(req) is dict and set(req) == {'schema','state_fingerprint','context','kind','request_id'}, 'request_fields')
    require(req == question(state, req['context'], req['kind']), 'stale_or_tampered_request')
    require(type(feedback) is dict and set(feedback) == {'schema','request_id','source','label'}, 'feedback_fields')
    require(feedback['schema'] == 'plm-ss-active3-feedback' and feedback['request_id'] == req['request_id'], 'feedback_request')
    require(feedback['source'] == 'external_teacher', 'prediction_is_not_teacher')
    require(type(feedback['label']) is str and feedback['label'] in LABELS, 'known_teacher_label')
    c = req['context']; y = int(feedback['label']); target = np.eye(4)[y]
    b = state.vectors([c])[0]
    scores = np.einsum('kd,kyd->ky', b, state.main.conj()).real / state.d
    state.main += .5*(target-scores.mean(axis=0))[None, :, None]*b[:, None, :]
    if req['kind'] == 'acquisition':
        if state.kind == 'pair':
            z = state.pair_vectors([c])[0]
            s = np.einsum('kyd,kd->ky', z, state.auxiliary.conj()).real/TRACE_D[state.kind]
            state.auxiliary += ((target-s.mean(axis=0))[None, :, None]*z).sum(axis=1)
        elif state.kind == 'bank':
            ab = state.vectors([c], True)[0]
            s = np.einsum('kd,kyd->ky', ab, state.auxiliary.conj()).real/TRACE_D[state.kind]
            state.auxiliary += (target-s.mean(axis=0))[None, :, None]*ab[:, None, :]
        state.acquired += 1
        post = state.raw([c])[0]
        key = context_id(c)
        state.ledger[key] = {'context': copy.deepcopy(c), 'last_step': state.step+1,
                             'post_margin': float(choice(post)['margin'][0]),
                             'visits': state.ledger.get(key, {}).get('visits', 0)+1}
    state.step += 1
    state.history = digest([state.history, req['request_id'], feedback])
    require(np.isfinite(state.main).all() and np.isfinite(state.auxiliary).all(), 'finite_update')
    return state


def teacher(req, label):
    return {'schema': 'plm-ss-active3-feedback', 'request_id': req['request_id'],
            'source': 'external_teacher', 'label': label}


def teach(state, context, label, kind='acquisition'):
    req = question(state, context, kind)
    return answer(state, req, teacher(req, label))
