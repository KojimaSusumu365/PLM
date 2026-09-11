"""Teacher-only coefficient learning. No unobserved-key targets are supplied."""
import numpy as np

METHODS = ('uniform', 'positive', 'residual', 'gain2')
RIDGE = 0.1
STEPS = 128
LOWER = 0.25
UPPER = 2.0


def coefficients(gram, targets, method):
    g = np.asarray(gram, dtype=np.float64)
    t = np.asarray(targets, dtype=np.float64)
    if method not in METHODS or g.ndim != 2 or g.shape[0] != g.shape[1] or t.ndim != 2 or t.shape[0] != len(g):
        raise ValueError('invalid_learning_input')
    if not np.isfinite(g).all() or not np.isfinite(t).all() or not np.all((t == 0) | (t == 1)) or not np.all(t.sum(axis=1) == 1):
        raise ValueError('invalid_targets')
    if not np.allclose(g, g.T, atol=1e-12, rtol=1e-12):
        raise ValueError('gram_must_be_symmetric')
    beta = t.copy()
    work_bytes = int(g.nbytes + t.nbytes + beta.nbytes)
    if method == 'gain2':
        beta *= 2
    elif method == 'positive':
        # Minimize .5||G[:,I_y] w - t_y||^2 + ridge/2||w-1||^2.
        # Fixed projected gradient; infinity norm bounds the Hessian norm.
        for y in range(t.shape[1]):
            idx = np.flatnonzero(t[:, y])
            if not len(idx):
                continue
            a = g[:, idx]
            h = a.T @ a + RIDGE * np.eye(len(idx))
            rhs = a.T @ t[:, y] + RIDGE
            lipschitz = float(np.max(np.abs(h).sum(axis=1)))
            w = np.ones(len(idx))
            for _ in range(STEPS):
                w = np.clip(w - (h @ w - rhs) / lipschitz, LOWER, UPPER)
            beta[idx, y] = w
            work_bytes = max(work_bytes, int(g.nbytes + t.nbytes + beta.nbytes + a.nbytes + h.nbytes + rhs.nbytes + w.nbytes))
    elif method == 'residual':
        # All observed keys may contribute signed corrections to each class.
        # Minimize .5||G B - T||_F^2 + ridge/2||B-T||_F^2.
        h = g.T @ g + RIDGE * np.eye(len(g))
        rhs = g.T @ t + RIDGE * t
        beta = np.linalg.solve(h, rhs)
        work_bytes = int(g.nbytes + t.nbytes + beta.nbytes + h.nbytes + rhs.nbytes)
    error_before = g @ t - t
    error_after = g @ beta - t
    penalty = RIDGE * float(np.sum((beta - t) ** 2))
    audit = {'method': method, 'known_keys': len(g), 'classes': t.shape[1],
             'initial_objective': float(.5 * np.sum(error_before ** 2)),
             'final_objective': float(.5 * np.sum(error_after ** 2) + .5 * penalty),
             'training_mse_before': float(np.mean(error_before ** 2)),
             'training_mse_after': float(np.mean(error_after ** 2)),
             'beta_min': float(beta.min()), 'beta_max': float(beta.max()),
             'negative_coefficients': int(np.sum(beta < 0)),
             'beta_bytes_training_only': int(beta.nbytes),
             'accounted_learning_arrays_bytes': work_bytes,
             'accounting_scope': 'Named arrays, not peak RSS/BLAS temporaries/energy.',
             'unobserved_keys_used_as_targets': False}
    return beta, audit


def learn(vectors, targets, method):
    b = np.asarray(vectors, dtype=np.complex128)
    if b.ndim != 2 or b.shape[1] < 1 or not np.isfinite(b).all():
        raise ValueError('invalid_vectors')
    if method in ('uniform', 'gain2'):
        t = np.asarray(targets, dtype=float)
        if t.ndim != 2 or t.shape[0] != len(b) or not np.all((t == 0) | (t == 1)) or not np.all(t.sum(axis=1) == 1):
            raise ValueError('invalid_targets')
        base = t.T @ b
        weights = base * (2 if method == 'gain2' else 1)
        before = (b @ base.conj().T).real / b.shape[1] - t
        after = (b @ weights.conj().T).real / b.shape[1] - t
        audit = {'method': method, 'known_keys': len(b), 'classes': t.shape[1],
                 'initial_objective': float(.5 * np.sum(before ** 2)),
                 'final_objective': float(.5 * np.sum(after ** 2)),
                 'training_mse_before': float(np.mean(before ** 2)), 'training_mse_after': float(np.mean(after ** 2)),
                 'beta_min': 0., 'beta_max': 2. if method == 'gain2' else 1., 'negative_coefficients': 0,
                 'beta_bytes_training_only': 0, 'accounted_learning_arrays_bytes': int(t.nbytes + base.nbytes + weights.nbytes + before.nbytes + after.nbytes),
                 'accounting_scope': 'Named arrays including common diagnostics; not peak RSS/BLAS temporaries/energy.',
                 'unobserved_keys_used_as_targets': False}
    else:
        gram = (b @ b.conj().T).real / b.shape[1]
        beta, audit = coefficients(gram, targets, method)
        weights = beta.T @ b
    audit['training_vector_bytes'] = int(b.nbytes)
    audit['memory_weight_bytes'] = int(weights.nbytes)
    audit['weight_energy'] = float(np.sum(np.abs(weights) ** 2))
    audit['weight_peak_amplitude'] = float(np.max(np.abs(weights)))
    return weights, audit
