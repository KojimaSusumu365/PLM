"""Single source of acceptance constants for the new release, not prior vendors."""
from types import MappingProxyType

MIN_SCORE = 0.65
MIN_MARGIN = 0.25
MIN_PRESENCE = 0.65
MIN_PROOF = 0.65
MAX_RESIDUAL = 0.20
LEGACY_MIN_SCORE = 0.60  # Unused legacy algebra.Memory, distinct original contract.
SELECTION_REQUIRED_ACCURACY = 1.0
NUMERIC_ATOL = 1e-12
NUMERIC_RTOL = 1e-12

def values():
    return {name: value for name, value in globals().items()
            if name.isupper() and isinstance(value, (int, float))}

POLICY = MappingProxyType(values())
