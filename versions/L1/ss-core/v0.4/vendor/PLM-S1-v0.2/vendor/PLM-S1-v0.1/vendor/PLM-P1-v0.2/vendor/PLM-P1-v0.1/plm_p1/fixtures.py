"""Explicitly artificial relation fixtures; no language-model gold or external corpus."""
from .core import symbol


def make_frames(count, *, document_id="synthetic:doc"):
    if type(count) is not int or not 0 <= count <= 128:
        raise ValueError("Synthetic count must be in [0,128]")
    frames = []
    for i in range(count):
        frames.append({"document_id": document_id, "event_id": f"event-{i:03d}",
                       "slots": {"subject": symbol("entity", f"animal-{2*i:03d}", document_id),
                                 "object": symbol("entity", f"animal-{2*i+1:03d}", document_id),
                                 "predicate": symbol("predicate", "chase" if i % 2 == 0 else "watch"),
                                 "polarity": symbol("state", "polarity:positive" if i % 3 else "polarity:negative"),
                                 "modality": symbol("state", "modality:asserted" if i % 4 else "modality:hypothetical"),
                                 "semantic_status": symbol("state", "semantic_status:rule_checked" if i % 5 else "semantic_status:quarantined"),
                                 "applied": symbol("state", "applied:false")},
                       "metadata": {"source": "hand_defined_synthetic_structure_not_semantic_evaluation",
                                    "subject_concept": "DOG", "object_concept": "DOG",
                                    "eligible_for_inference": False}})
    return frames


def entity_candidates(count=96, *, document_id="synthetic:doc"):
    return [symbol("entity", f"animal-{i:03d}", document_id) for i in range(count)]
