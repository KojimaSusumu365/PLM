"""S1 boundary: numerical observation packet without the correct slot assignments."""
from copy import deepcopy
import numpy as np
from .core import ALGORITHM, CODEC, PhaseCodebook, require, digest, signal_array, observation_mask

FORMAT = "PLM-P1-S1-observation-packet-v1"


def to_packet(samples, mask, codebook, *, source_refs=None):
    values = signal_array(samples, codebook.dimension)
    observed = observation_mask(mask, codebook.dimension)
    # Unknown components must not carry original unmasked ground truth.
    values[~observed] = 0
    refs = deepcopy(source_refs) if source_refs is not None else []
    payload = {"format": FORMAT, "producer_version": "PLM-P1 v0.1", "codec": CODEC,
               "codebook": codebook.spec, "codebook_fingerprint": codebook.fingerprint,
               "samples": {"real": values.real.tolist(), "imag": values.imag.tolist()},
               "observed_mask": observed.tolist(), "source_refs": refs,
               "normalization": "unnormalized_sum_unit_phasor_bindings",
               "phase_reference": "aligned_baseband_required_not_estimated",
               "time_axis": None, "chip_rate_hz": None,
               "boundary": {"mode": "observe_only", "inference_enabled": False,
                            "independent_semantic_validation": "not_performed",
                            "ss_demodulation_implemented": False}}
    payload["payload_hash"] = digest(payload)
    from_packet(payload)  # also validate source references before returning
    return payload


def from_packet(packet, *, expected_codebook=None):
    require(type(packet) is dict, "Packet must be object")
    fields = {"format", "producer_version", "codec", "codebook", "codebook_fingerprint", "samples",
              "observed_mask", "source_refs", "normalization", "phase_reference", "time_axis", "chip_rate_hz", "boundary", "payload_hash"}
    require(set(packet) == fields, "Unsupported packet fields (slot assignments/ground truth are prohibited)")
    body = {k: v for k, v in packet.items() if k != "payload_hash"}
    require(packet["payload_hash"] == digest(body), "Packet checksum mismatch")
    require(packet["format"] == FORMAT and packet["producer_version"] == "PLM-P1 v0.1" and packet["codec"] == CODEC, "Unsupported wire version/codec")
    require(packet["boundary"] == {"mode": "observe_only", "inference_enabled": False,
                                  "independent_semantic_validation": "not_performed", "ss_demodulation_implemented": False}, "Boundary violation")
    require(packet["boundary"]["inference_enabled"] is False and packet["boundary"]["ss_demodulation_implemented"] is False, "Boundary flags must be false booleans")
    spec = packet["codebook"]
    require(type(spec) is dict and set(spec) == {"algorithm", "dimension", "seed", "symbol_serialization", "phase_units"}, "Invalid codebook specification")
    codebook = PhaseCodebook(spec["dimension"], spec["seed"])
    require(spec == codebook.spec and spec["algorithm"] == ALGORITHM, "Unsupported codebook")
    require(packet["codebook_fingerprint"] == codebook.fingerprint, "Codebook fingerprint mismatch")
    if expected_codebook is not None:
        require(codebook.fingerprint == expected_codebook.fingerprint, "Receiver codebook mismatch")
    require(packet["normalization"] == "unnormalized_sum_unit_phasor_bindings" and
            packet["phase_reference"] == "aligned_baseband_required_not_estimated" and
            packet["time_axis"] is None and packet["chip_rate_hz"] is None, "Unsupported signal conventions")
    samples = packet["samples"]
    require(type(samples) is dict and set(samples) == {"real", "imag"}, "Invalid complex signal fields")
    for array in samples.values():
        require(type(array) is list and len(array) == codebook.dimension and all(type(v) in (int, float) for v in array), "Invalid signal array")
    values = signal_array(np.asarray(samples["real"]) + 1j * np.asarray(samples["imag"]), codebook.dimension)
    observed = observation_mask(packet["observed_mask"], codebook.dimension)
    require(np.all(values[~observed] == 0), "Masked samples must be zero; do not leak hidden components")
    refs = packet["source_refs"]
    require(type(refs) is list, "Invalid source reference list")
    seen = set()
    for ref in refs:
        require(type(ref) is dict and set(ref) == {"document_id", "event_id", "source_record_hash"}, "Source reference contains unsupported fields")
        require(all(type(v) is str and v for v in ref.values()), "Invalid source reference")
        key = (ref["document_id"], ref["event_id"])
        require(key not in seen, "Duplicate source reference")
        seen.add(key)
        require(len(ref["source_record_hash"]) == 64 and all(c in "0123456789abcdef" for c in ref["source_record_hash"]), "Invalid record hash")
    return values, observed, codebook
