"""Numerical meaning-code bridge into the frozen v0.1 generator.

The bridge recovers the new reader's signal, then rebinds the selected symbols
using the fixed generator codebook. No text, gold, teacher traces or grammar
decisions are supplied to the generator.
"""
import numpy as np
from .runtime import ROLES, abstain


def translate(reader, packet, frozen_generator):
    recovered = reader.recover(packet)
    if recovered["status"] != "recovered":
        return abstain(recovered["reason"], packet=None)
    vector = np.zeros(frozen_generator.book.dimension, dtype=np.complex128)
    for role in ROLES:
        value = recovered["slots"][role]
        if value not in frozen_generator.meta["slot_candidates"][role]:
            return abstain("unsupported_generator_vocabulary", packet=None)
        vector += frozen_generator.role(role) * frozen_generator.book.code("value", value)
    return {"status": "bridged", "packet": frozen_generator.pack(vector), "eligible_for_inference": False}


def generate(reader, packet, frozen_generator, goal="object_first"):
    bridged = translate(reader, packet, frozen_generator)
    if bridged["status"] != "bridged":
        return abstain(bridged["reason"], text=None)
    return frozen_generator.generate(bridged["packet"], goal)
