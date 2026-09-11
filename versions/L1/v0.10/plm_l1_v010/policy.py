"""Pre-evaluation operating policy. Scores are not posterior probabilities."""
MAX_CANDIDATES=4
MAX_TRAIN_LOSS=0.25
TRAIN_SLACK=0.125
MAX_VALIDATION_LOSS=0.25
VALIDATION_SLACK=0.0
MIN_TRAIN_COVERAGE=0.5
ABSTENTION_LOSS=0.5
DEFAULT_RISK_TARGET=0.10

def values():
    return {k:v for k,v in globals().items() if k.isupper() and type(v) in (int,float)}
