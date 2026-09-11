"""Prediction-only selector: model and unlabeled contexts, never teacher answers."""
import copy
import hashlib
import numpy as np
from ss_multicode.algebra import digest, require
from ss_multicode.model import Model

STRATEGIES = ('random', 'ambiguity', 'disagreement')


def context_id(context):
    Model.validate(context)
    return digest(['ss-active-context-01', context])


def normalize_pool(pool):
    require(type(pool) is list and len(pool) <= 512, 'pool_list_max512')
    result = []
    for row in pool:
        require(type(row) is dict and set(row) == {'id', 'context'}, 'unlabeled_pool_only')
        require(type(row['id']) is str and row['id'] == context_id(row['context']), 'context_only_id_required')
        result.append(copy.deepcopy(row))
    require(len({r['id'] for r in result}) == len(result), 'duplicate_pool_context')
    return sorted(result, key=lambda r: r['id'])


def diagnostics(readers):
    x = np.asarray(readers, dtype=float)
    require(x.ndim == 3 and x.shape[1:] == (4, 4) and np.isfinite(x).all(), 'four_bank_scores')
    mean = x.mean(axis=1); order = np.argsort(-mean, axis=1, kind='stable')
    rows = np.arange(len(x)); margin = mean[rows, order[:, 0]] - mean[rows, order[:, 1]]
    bo = np.argsort(-x, axis=2, kind='stable')
    top = bo[:, :, 0]; bankgap = np.take_along_axis(x, bo[:, :, :1], axis=2)[:, :, 0] - np.take_along_axis(x, bo[:, :, 1:2], axis=2)[:, :, 0]
    votes = np.eye(4)[top]; tied = bankgap <= 1e-12
    votes[tied] = .25
    proportions = votes.mean(axis=1); gini = 1 - (proportions ** 2).sum(axis=1)
    return {'margin': margin, 'gini': gini, 'bank_choices': np.where(tied, -1, top), 'mean': mean}


def select(model, pool, strategy='random', seed='acq-0', index=0):
    require(model.architecture == 'concat512', 'shared_residual_model_required')
    require(strategy in STRATEGIES and type(seed) is str and 0 < len(seed) <= 80 and type(index) is int and index >= 0, 'selection_parameters')
    rows = normalize_pool(pool); require(bool(rows), 'pool_exhausted')
    ties = [digest(['ss-active-order-01', seed, r['id']]) for r in rows]
    if strategy == 'random':
        chosen = min(range(len(rows)), key=lambda i: (ties[i], rows[i]['id']))
        scored = [rows[chosen]]; score_index = 0
        raw = model.raw([rows[chosen]['context']])['readers']; d = diagnostics(raw)
        priority = None
    else:
        scored = rows; raw = model.raw([r['context'] for r in rows])['readers']; d = diagnostics(raw)
        values = d['margin'] if strategy == 'ambiguity' else -d['gini']
        chosen = min(range(len(rows)), key=lambda i: (float(values[i]), ties[i], rows[i]['id']))
        score_index = chosen; priority = float(d['margin'][chosen] if strategy == 'ambiguity' else d['gini'][chosen])
    item = rows[chosen]
    result = {'schema': 'plm-ss-active-selection-01', 'model_fingerprint': model.fingerprint, 'pool_digest': digest(rows),
              'strategy': strategy, 'seed': seed, 'index': index, 'selected_id': item['id'], 'context': item['context'],
              'diagnostics': {'priority': priority, 'mean_margin': float(d['margin'][score_index]), 'gini': float(d['gini'][score_index]),
                              'bank_choices': d['bank_choices'][score_index].tolist(), 'mean_scores': d['mean'][score_index].tolist(),
                              'tie_key': ties[chosen], 'contexts_scored_this_call': len(scored),
                              'scored_ids_digest': digest([r['id'] for r in scored]),
                              'raw_scores_digest': hashlib.sha256(raw.astype('<f8').tobytes()).hexdigest(),
                              'score_is_probability': False}, 'eligible_for_inference': False}
    result['selection_id'] = digest(result)
    return result
