import time
from plm_l1_v011.algebra import digest, require
from plm_l1_v011.core import rows_checked
from plm_l1_v011.training import fit, calibrate
from .core import GuardedModel, MAX_COMPLETIONS
from .evidence import build_evidence


def attach(base, train, *, max_completions=MAX_COMPLETIONS):
    rows_checked(train, base.config['fields'])
    require(digest(train) == base.training['train_digest'], 'witness_teacher_must_match_base_training')
    started = time.perf_counter()
    memories = [build_evidence(train, m['mask'], base.config['labels'], m['dimension'],
                              'v012-witness/' + base.config['seed'], base.config['backend']) for m in base.members]
    guard = GuardedModel(base, memories, {'train_digest': digest(train), 'rows': len(train),
                                        'uses_training_only': True, 'deduplicated_per_key_label': True,
                                        'calibration_or_evaluation_rows_added': False}, max_completions)
    return guard, {'attach_seconds': time.perf_counter() - started}


def train_model(train, selection, calibration, *, representation='hybrid3', selector='validation',
                backend='ss', dimension=2048, seed='development-0', max_completions=MAX_COMPLETIONS):
    base, audit, perf = fit(train, selection, representation=representation, selector=selector,
                            backend=backend, dimension=dimension, seed=seed)
    calibrate(base, calibration)
    guard, extra = attach(base, train, max_completions=max_completions)
    return guard, audit, dict(perf, **extra)
