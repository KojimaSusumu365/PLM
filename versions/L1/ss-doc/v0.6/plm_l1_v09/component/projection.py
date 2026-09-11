"""Train-only categorical dependency selection, phase-only leaf lookup.

The dependency selector is conventional symbolic training machinery. At runtime
no tree, leaf feature values, or key->target table are retained. Learned masks
and candidate inventories are public model metadata; decisions use correlation.
"""
import json
import math
from collections import Counter
import numpy as np
from ..thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MIN_PROOF, MAX_RESIDUAL, LEGACY_MIN_SCORE

from .algebra import canonical, require


def structure_code(book, value, domain="target"):
    if isinstance(value, list):
        out = book.code("sequence_length:" + domain, len(value)).copy()
        for i, item in enumerate(value):
            out *= np.roll(structure_code(book, item, domain + "/item:" + str(i)), 17 * i)
        return out
    return book.code("atom:" + domain, value)


class Space:
    def __init__(self, book):
        self.book, self.cache = book, {}

    def key(self, fields):
        identity = canonical(fields)
        if identity not in self.cache:
            out = self.book.code("field_set", sorted(fields)).copy()
            for field in sorted(fields):
                # Values are encoded in field-specific namespaces. Multiplying
                # an independent field code and a shared value code would lose
                # assignments when values are swapped between two fields.
                out *= structure_code(self.book, fields[field], "field:" + field)
            self.cache[identity] = out
        return self.cache[identity]

    def target(self, label):
        try:
            value = json.loads(label)
        except (json.JSONDecodeError, TypeError):
            value = label
        return self.book.code("target_namespace", "target") * structure_code(self.book, value)


def dependency_leaves(observations, partial=True):
    """Deterministic ID3-style partition on deduplicated context/target pairs.

    Information gain, then smaller arity and canonical field name break ties.
    Leaf conjunctions become partial projection associations, not runtime rules.
    """
    require(type(partial) is bool and bool(observations), "invalid_observations")
    unique = {}
    fields = set(observations[0][0])
    for context, label in observations:
        require(set(context) == fields and type(label) is str, "invalid_context_schema")
        key = canonical(context)
        require(key not in unique or unique[key][1] == label, "conflicting_complete_context")
        unique[key] = (context, label)
    rows = [unique[k] for k in sorted(unique)]
    if not partial:
        return rows

    def entropy(part):
        counts = Counter(label for _, label in part)
        return -sum((n / len(part)) * math.log2(n / len(part)) for n in counts.values())

    def visit(part, remaining, path):
        if len({label for _, label in part}) == 1:
            # Positive-only support is not evidence for universal support.
            return [(dict(path), part[0][1])] if path else part
        require(bool(remaining), "unresolved_labels")
        options = []
        for field in sorted(remaining):
            groups = {}
            for context, label in part:
                groups.setdefault(canonical(context[field]), []).append((context, label))
            if len(groups) < 2:
                continue
            gain = entropy(part) - sum(len(group) / len(part) * entropy(group) for group in groups.values())
            options.append((-round(gain, 12), len(groups), field, groups))
        require(bool(options), "no_dependency_split")
        _, _, field, groups = min(options, key=lambda row: row[:3])
        result = []
        for key in sorted(groups):
            result += visit(groups[key], remaining - {field}, dict(path, **{field: json.loads(key)}))
        return result
    return visit(rows, fields, {})


class ProjectionMemory:
    def __init__(self, space, groups):
        self.space, self.groups, self.cache = space, [], {}
        for mask, vector, candidates in groups:
            mask = tuple(mask)
            vector = np.asarray(vector, dtype=np.complex128).copy()
            require(vector.shape == (space.book.dimension,) and np.isfinite(vector).all(), "invalid_weights")
            candidates = tuple(sorted(set(candidates)))
            require(bool(candidates), "empty_candidates")
            basis = np.array([space.target(c).conj() for c in candidates])
            self.groups.append((mask, vector, candidates, basis))

    def recall(self, context):
        identity = canonical(context)
        if identity not in self.cache:
            accepted, audits = set(), []
            for mask, vector, candidates, basis in self.groups:
                require(all(field in context for field in mask), "missing_query_field")
                key = {field: context[field] for field in mask}
                scores = np.real(basis @ (vector * self.space.key(key))) / self.space.book.dimension
                order = np.argsort(-scores, kind="stable")
                top = float(scores[order[0]])
                runner = max(0., float(scores[order[1]])) if len(order) > 1 else 0.
                good = top >= MIN_SCORE and top - runner >= MIN_MARGIN
                if good:
                    accepted.add(candidates[order[0]])
                audits.append({"mask": list(mask), "value": candidates[order[0]] if good else None,
                               "score": round(top, 8), "margin": round(top-runner, 8)})
            self.cache[identity] = {"value": next(iter(accepted)) if len(accepted) == 1 else None,
                                    "reason": "recalled" if len(accepted) == 1 else "weak_or_conflicting_projection", "projections": audits}
        return json.loads(canonical(self.cache[identity]))


def fit_memory(space, observations, partial=True, enabled=True):
    leaves = dependency_leaves(observations, partial)
    require(len(leaves) <= 256, "memory_capacity_exceeded")
    masks = sorted({tuple(sorted(context)) for context, _ in leaves})
    groups = []
    for mask in masks:
        selected = [(c, t) for c, t in leaves if tuple(sorted(c)) == mask]
        vector = np.zeros(space.book.dimension, dtype=np.complex128)
        if enabled:
            for context, label in sorted(selected, key=canonical):
                vector += space.key(context).conj() * space.target(label)
        groups.append((mask, vector, sorted({t for _, t in selected})))
    stats = {"observations": len(observations), "complete_contexts": len({canonical(c) for c, _ in observations}),
             "projected_contexts": len(leaves), "masks": [list(m) for m in masks], "vectors": len(groups)}
    return ProjectionMemory(space, groups), stats
