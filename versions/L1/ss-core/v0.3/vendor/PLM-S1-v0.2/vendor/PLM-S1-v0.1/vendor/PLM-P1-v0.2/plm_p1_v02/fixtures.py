"""Predeclared synthetic vocabulary/address namespace, independent of slot truth."""
from plm_p1.core import symbol
from plm_p1.fixtures import make_frames, entity_candidates

DOC = "synthetic:doc"


def public_catalogue(capacity=4, document_id=DOC):
    # Includes addresses with no transmitted event, deliberately not an occupancy map.
    ids = [f"event-{i:03d}" for i in range(capacity)] + [f"absent-event-{i:03d}" for i in range(4)]
    vocab = {"predicate": [symbol("predicate", s) for s in ("chase", "watch", "follow")],
             "polarity": [symbol("state", "polarity:" + s) for s in ("positive", "negative")],
             "modality": [symbol("state", "modality:" + s) for s in ("asserted", "hypothetical")],
             "semantic_status": [symbol("state", "semantic_status:" + s) for s in ("rule_checked", "quarantined")],
             "applied": [symbol("state", "applied:" + s) for s in ("false", "true")]}
    return {"format": "plm-public-nuisance-catalogue-v1", "addresses": [{"document_id": document_id, "event_id": e} for e in ids], "vocabulary": vocab}
