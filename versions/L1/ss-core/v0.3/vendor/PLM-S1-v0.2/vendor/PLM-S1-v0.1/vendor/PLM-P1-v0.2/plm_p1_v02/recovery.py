"""Masked nuisance-subspace rejection with observation-conditioned decisions.

The public catalogue is possibilities, not actual event/slot occupancy. In
particular absence from it is NEVER used as evidence that a query is absent.
"""
from dataclasses import dataclass, asdict
from statistics import NormalDist
import math
import numpy as np
from plm_p1.core import (canonical, digest, require, address, validate_symbol,
                         signal_array, observation_mask, ROLES)

NUISANCE_ROLES = {"predicate", "polarity", "modality", "semantic_status", "applied"}


def validate_catalogue(catalogue):
    require(type(catalogue) is dict and set(catalogue) == {"format", "addresses", "vocabulary"}, "Invalid public catalogue; assignments/gold prohibited")
    require(catalogue["format"] == "plm-public-nuisance-catalogue-v1", "Unknown catalogue")
    refs, vocab = catalogue["addresses"], catalogue["vocabulary"]
    require(type(refs) is list and len(refs) <= 64, "Invalid address catalogue")
    seen = set()
    for ref in refs:
        require(type(ref) is dict and set(ref) == {"document_id", "event_id"}, "Address must not disclose occupancy")
        key = address(**ref)
        require(key not in seen, "Duplicate public address")
        seen.add(key)
    require(type(vocab) is dict and set(vocab) <= NUISANCE_ROLES, "Only declared nuisance roles supported")
    for role, values in vocab.items():
        require(type(values) is list and 1 <= len(values) <= 32, "Invalid nuisance vocabulary")
        keys = set()
        for value in values:
            validate_symbol(value)
            require(value["scope"] == "global", "Nuisance vocabulary must be global")
            require(value["kind"] == ("predicate" if role == "predicate" else "state"), "Nuisance kind mismatch")
            key = canonical(value)
            require(key not in keys, "Duplicate nuisance candidate")
            keys.add(key)
    require(len(refs) * sum(map(len, vocab.values())) <= 1024, "Catalogue too large")
    return catalogue


@dataclass(frozen=True)
class AdaptivePolicy:
    min_components: int = 128
    min_residual_dof: int = 128
    min_retained_fraction: float = 0.5
    min_amplitude: float = 0.40
    family_alpha: float = 0.01
    min_margin: float = 0.10
    gap_z: float = 1.5

    def validate(self):
        for k in ("min_components", "min_residual_dof"):
            require(type(getattr(self, k)) is int and getattr(self, k) >= 1, "Invalid count policy")
        for k in ("min_retained_fraction", "min_amplitude", "family_alpha", "min_margin", "gap_z"):
            v = getattr(self, k)
            require(type(v) in (int, float) and math.isfinite(v) and v > 0, "Invalid finite positive policy")
        require(self.min_retained_fraction <= 1 and 1e-8 <= self.family_alpha < 0.5, "Invalid policy range")


def candidate_list(candidates):
    require(type(candidates) is list and len(candidates) <= 4096, "Invalid candidate dictionary")
    pairs = []
    for value in candidates:
        validate_symbol(value)
        pairs.append((canonical(value), value))
    require(len({k for k, _ in pairs}) == len(pairs), "Duplicate candidate")
    return [v for _, v in sorted(pairs)]


class Receiver:
    """No frames, truth map, channel seed or true phase enters this object."""
    def __init__(self, samples, mask, codebook, catalogue, *, project=True):
        require(type(project) is bool, "project must be boolean")
        self.book = codebook
        self.values = signal_array(samples, codebook.dimension)
        self.mask = observation_mask(mask, codebook.dimension)
        # Defensive copy prevents mutation of externally supplied dictionaries.
        import json
        self.catalogue = json.loads(canonical(validate_catalogue(catalogue)))
        self.project = project
        self._contexts = {}

    def context(self, document_id, event_id, role):
        exclude = (document_id, event_id, role) if role in NUISANCE_ROLES else None
        if exclude in self._contexts:
            return self._contexts[exclude]
        y = self.values[self.mask]
        n = len(y)
        columns = []
        if self.project and n:
            for ref in sorted(self.catalogue["addresses"], key=lambda r: address(**r)):
                for nuisance_role, candidates in sorted(self.catalogue["vocabulary"].items()):
                    if (ref["document_id"], ref["event_id"], nuisance_role) == exclude:
                        continue
                    key = self.book.key(**ref, role=nuisance_role)[self.mask]
                    for candidate in candidate_list(candidates):
                        columns.append(key * self.book.value(candidate)[self.mask])
        # At/above full rank: fail closed before expensive decomposition.
        if len(columns) >= n and n:
            q = None
            rank, residual = n, np.zeros_like(y)
        elif columns:
            matrix = np.column_stack(columns)
            # SVD handles duplicate/linearly dependent nuisance directions safely.
            u, s, _ = np.linalg.svd(matrix, full_matrices=False)
            rank = int(np.sum(s > max(matrix.shape) * np.finfo(float).eps * s[0]))
            q = u[:, :rank]
            residual = y - q @ (q.conj().T @ y)
        else:
            q = np.empty((n, 0), complex)
            rank, residual = 0, y.copy()
        require(np.isfinite(residual).all(), "Projection overflow")
        context = q, residual, rank
        self._contexts[exclude] = context
        return context

    def scores(self, document_id, event_id, role, candidates, policy=AdaptivePolicy()):
        policy.validate()
        address(document_id, event_id)
        require(role in ROLES, "Unknown role")
        choices = candidate_list(candidates)
        n = int(self.mask.sum())
        base = {"status": "abstain", "selected": None, "reason": None,
                "observed_components": n, "candidate_count": len(choices),
                "eligible_for_inference": False, "top_candidates": [], "margin": None,
                "score_kind": "projected_coherent_amplitude_not_probability",
                "catalogue_hash": digest(self.catalogue), "policy": asdict(policy),
                "nuisance_rank": 0, "residual_dof": n, "residual_power": None,
                "amplitude_threshold": None, "margin_threshold": None}
        if n < policy.min_components:
            return dict(base, reason="insufficient_observed_components")
        if not choices:
            return dict(base, reason="empty_candidate_dictionary")
        q, y, rank = self.context(document_id, event_id, role)
        dof = n - rank
        base.update(nuisance_rank=rank, residual_dof=dof)
        if dof < policy.min_residual_dof:
            return dict(base, reason="insufficient_residual_degrees_of_freedom")
        a = np.column_stack([self.book.key(document_id, event_id, role)[self.mask] * self.book.value(c)[self.mask] for c in choices])
        t = a - q @ (q.conj().T @ a) if rank else a
        energy = np.sum(np.abs(t) ** 2, axis=0)
        if np.any(energy < n * policy.min_retained_fraction):
            return dict(base, reason="candidate_subspace_too_depleted")
        estimates = np.real(t.conj().T @ y) / energy
        power = float(np.vdot(y, y).real / dof)
        require(np.isfinite(estimates).all() and math.isfinite(power), "Nonfinite scores")
        order = sorted(range(len(choices)), key=lambda i: (-estimates[i], canonical(choices[i])))
        best = order[0]
        second = order[1] if len(order) > 1 and estimates[order[1]] > 0 else None
        margin = float(estimates[best] - (estimates[second] if second is not None else 0))
        z = NormalDist().inv_cdf(1 - policy.family_alpha / len(choices))
        amp_threshold = max(policy.min_amplitude, z * math.sqrt(power / (2 * energy[best])))
        diff = t[:, best] / energy[best]
        if second is not None:
            diff = diff - t[:, second] / energy[second]
        gap_threshold = max(policy.min_margin, policy.gap_z * math.sqrt(power * float(np.vdot(diff, diff).real) / 2))
        base.update(top_candidates=[{"symbol": choices[i], "score": round(float(estimates[i]), 8)} for i in order[:5]],
                    margin=round(margin, 8), residual_power=round(power, 8),
                    amplitude_threshold=round(amp_threshold, 8), margin_threshold=round(gap_threshold, 8))
        if estimates[best] < amp_threshold:
            return dict(base, reason="amplitude_below_observation_conditioned_threshold")
        if margin < gap_threshold:
            return dict(base, reason="ambiguous_candidates")
        return dict(base, status="recovered", selected=choices[best], reason="numerical_recovery_only")
