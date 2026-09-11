"""Role/event binding with unit complex phasors and masked coherent correlation."""
from dataclasses import dataclass
from hashlib import sha256, shake_256
import json
import math
import numpy as np

ALGORITHM = "shake256-u53-unit-phase-v1"
CODEC = "event-role-hadamard-sum-v1"
ROLES = ("subject", "object", "predicate", "polarity", "modality", "semantic_status", "applied", "target_clause")
KINDS = {"entity", "concept", "predicate", "state", "clause"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def symbol(kind, identity, scope="global"):
    value = {"kind": kind, "id": identity, "scope": scope}
    validate_symbol(value)
    return value


def validate_symbol(value):
    require(type(value) is dict and set(value) == {"kind", "id", "scope"}, "Invalid symbol fields")
    require(value["kind"] in KINDS and all(type(value[k]) is str and value[k].strip() for k in value), "Invalid symbol")


def address(document_id, event_id):
    require(all(type(s) is str and s.strip() for s in (document_id, event_id)), "Document/event ID required")
    return canonical([document_id, event_id])


def validate_frames(frames):
    require(type(frames) is list, "Frames must be a list")
    seen = set()
    for frame in frames:
        require(type(frame) is dict and set(frame) == {"document_id", "event_id", "slots", "metadata"}, "Invalid frame fields")
        key = address(frame["document_id"], frame["event_id"])
        require(key not in seen, "Duplicate event address; never superpose conflicting versions silently")
        seen.add(key)
        require(type(frame["slots"]) is dict and frame["slots"] and set(frame["slots"]) <= set(ROLES), "Invalid/empty slots")
        for role, value in frame["slots"].items():
            validate_symbol(value)
            if value["kind"] in {"entity", "clause"}:
                require(value["scope"] == frame["document_id"], "Local identity scope must match document")
            if role in {"polarity", "modality", "semantic_status", "applied"}:
                require(value["kind"] == "state", "State role requires state symbol")
        meta = frame["metadata"]
        require(type(meta) is dict and meta.get("eligible_for_inference") is False, "Inference is prohibited")
        canonical(meta)


class PhaseCodebook:
    def __init__(self, dimension=2048, seed="plm-p1-v01"):
        require(type(dimension) is int and 128 <= dimension <= 16384 and dimension % 64 == 0, "Dimension must be a multiple of 64 in [128,16384]")
        require(type(seed) is str and seed.strip(), "Seed required")
        self.dimension, self.seed, self._cache = dimension, seed, {}

    @property
    def spec(self):
        return {"algorithm": ALGORITHM, "dimension": self.dimension, "seed": self.seed,
                "symbol_serialization": "canonical-json-utf8-v1", "phase_units": "radians"}

    @property
    def fingerprint(self):
        return digest(self.spec)

    def code(self, namespace, identifier):
        require(namespace in {"event", "role", "symbol"}, "Unknown code namespace")
        key = canonical([ALGORITHM, self.seed, namespace, identifier])
        if key not in self._cache:
            # Fixed byte stream, little-endian integer and 53-bit fraction.
            # Dimensions share prefixes; CPython's randomized hash() is never used.
            raw = shake_256(key.encode("utf-8")).digest(8 * self.dimension)
            fractions = (np.frombuffer(raw, dtype="<u8") >> 11).astype(np.float64) * (2.0 ** -53)
            phase = fractions * (2.0 * np.pi)
            values = np.cos(phase) + 1j * np.sin(phase)
            values.setflags(write=False)
            self._cache[key] = values
        return self._cache[key].copy()

    def value(self, value):
        validate_symbol(value)
        return self.code("symbol", value)

    def key(self, document_id, event_id, role):
        require(role in ROLES, "Unknown role")
        return self.code("event", address(document_id, event_id)) * self.code("role", role)


def encode(frames, codebook, *, bind_roles=True, bind_events=True):
    validate_frames(frames)
    require(type(bind_roles) is bool and type(bind_events) is bool, "Ablation switches must be booleans")
    samples = np.zeros(codebook.dimension, dtype=np.complex128)
    # Stable summation order; reordered input frames/slot dictionaries are equivalent.
    for frame in sorted(frames, key=lambda f: address(f["document_id"], f["event_id"])):
        event = codebook.code("event", address(frame["document_id"], frame["event_id"])) if bind_events else 1
        for role, value in sorted(frame["slots"].items()):
            role_code = codebook.code("role", role) if bind_roles else 1
            samples += event * role_code * codebook.value(value)
    return samples


@dataclass(frozen=True)
class DecodePolicy:
    min_components: int = 64
    min_score: float = 0.65
    min_margin: float = 0.20

    def validate(self):
        require(type(self.min_components) is int and self.min_components >= 1, "Invalid minimum components")
        require(type(self.min_score) in (int, float) and math.isfinite(self.min_score) and self.min_score > 0, "Invalid score threshold")
        require(type(self.min_margin) in (int, float) and math.isfinite(self.min_margin) and self.min_margin > 0, "Invalid margin threshold")


def signal_array(samples, dimension):
    array = np.asarray(samples)
    require(array.ndim == 1 and len(array) == dimension and array.dtype.kind in "fci", "Signal shape/type mismatch")
    require(np.isfinite(array).all(), "Nonfinite signal")
    return array.astype(np.complex128, copy=True)


def observation_mask(mask, dimension):
    if mask is None:
        return np.ones(dimension, dtype=bool)
    array = np.asarray(mask)
    require(array.shape == (dimension,) and array.dtype.kind == "b", "Mask must contain boolean values")
    return array.copy()


def decode(samples, codebook, document_id, event_id, role, candidates, *, mask=None,
           policy=DecodePolicy(), bind_roles=True, bind_events=True):
    """Reads ONLY samples, query keys and the supplied candidate dictionary, not frames.

    Score = real(mean(y * conj(event * role * candidate))) on observed components.
    It is a matched-filter amplitude, not a normalized cosine or a probability.
    """
    policy.validate()
    address(document_id, event_id)
    require(role in ROLES, "Unknown role")
    require(type(bind_roles) is bool and type(bind_events) is bool, "Invalid ablation switches")
    values = signal_array(samples, codebook.dimension)
    observed = observation_mask(mask, codebook.dimension)
    require(type(candidates) is list, "Candidate list required")
    keyed = {}
    for candidate in candidates:
        validate_symbol(candidate)
        key = canonical(candidate)
        require(key not in keyed, "Duplicate candidate")
        keyed[key] = candidate
    count = int(observed.sum())
    base = {"status": "abstain", "selected": None, "observed_components": count,
            "candidate_count": len(keyed), "score_kind": "coherent_matched_filter_amplitude_not_probability",
            "eligible_for_inference": False, "top_candidates": [], "margin": None}
    if count < policy.min_components:
        return dict(base, reason="insufficient_observed_components")
    if not keyed:
        return dict(base, reason="empty_candidate_dictionary")
    event = codebook.code("event", address(document_id, event_id)) if bind_events else np.ones(codebook.dimension)
    role_code = codebook.code("role", role) if bind_roles else np.ones(codebook.dimension)
    unbound = values[observed] * np.conj((event * role_code)[observed])
    scored = []
    for key, candidate in sorted(keyed.items()):
        score = float(np.real(np.mean(unbound * np.conj(codebook.value(candidate)[observed]))))
        require(math.isfinite(score), "Correlation overflow/nonfinite score")
        scored.append((score, key, candidate))
    scored.sort(key=lambda row: (-row[0], row[1]))
    best, _, selected = scored[0]
    # An explicit null hypothesis (no component at this address) has score zero.
    runner_up = max(0.0, scored[1][0]) if len(scored) > 1 else 0.0
    margin = best - runner_up
    base.update(top_candidates=[{"symbol": c, "score": round(s, 8)} for s, _, c in scored[:5]], margin=round(margin, 8))
    if best < policy.min_score:
        return dict(base, reason="score_below_threshold")
    if margin < policy.min_margin:
        return dict(base, reason="ambiguous_candidates")
    return dict(base, status="recovered", selected=selected, reason="numerical_recovery_only")


def channel(samples, *, seed, keep_fraction=1.0, noise_std=0.0, phase_offset=0.0, jitter_std=0.0):
    """Synthetic test channel; true perturbation values belong to evaluator, not decoder."""
    require(type(seed) is int and seed >= 0, "Channel seed must be nonnegative integer")
    for x in (keep_fraction, noise_std, phase_offset, jitter_std):
        require(type(x) in (int, float) and math.isfinite(x), "Invalid channel parameter")
    require(0 <= keep_fraction <= 1 and noise_std >= 0 and jitter_std >= 0, "Invalid channel range")
    values = signal_array(samples, len(samples))
    rng = np.random.Generator(np.random.PCG64(seed))
    size = len(values)
    mask = np.zeros(size, dtype=bool)
    count = int(round(size * keep_fraction))
    mask[rng.permutation(size)[:count]] = True
    values *= np.exp(1j * (phase_offset + rng.normal(0, jitter_std, size)))
    values += noise_std / np.sqrt(2) * (rng.normal(size=size) + 1j * rng.normal(size=size))
    values[~mask] = 0
    return values, mask
