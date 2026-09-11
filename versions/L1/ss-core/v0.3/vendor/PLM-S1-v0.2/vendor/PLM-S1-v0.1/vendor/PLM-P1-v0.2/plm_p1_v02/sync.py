"""Pilot-only global phase synchronization prototype, NOT SS demodulation.

Pilot coordinates consume the SAME D-coordinate frame and energy budget.
There is no delay, frequency-offset estimator, time axis or chip spreading.
"""
import math
import numpy as np
from plm_p1.core import PhaseCodebook, signal_array, observation_mask, require, digest

FORMAT = "PLM-P1-pilot-phase-packet-v2"
BOUNDARY = {"mode": "observe_only", "inference_enabled": False,
            "independent_semantic_validation": "not_performed",
            "ss_demodulation_implemented": False, "synchronization_scope": "global_phase_only"}


def pilot_sequence(book, length):
    return book.code("role", "s1-public-pilot-v1")[-length:]


def pilot_frame(samples, book, *, pilot_length=128, rms=math.sqrt(28)):
    """Transmitter: no channel truth, public gain balances the payload energy."""
    require(type(pilot_length) is int and 16 <= pilot_length <= book.dimension // 4, "Invalid pilot length")
    require(type(rms) in (int, float) and math.isfinite(rms) and rms > 0, "Invalid RMS")
    values = signal_array(samples, book.dimension)
    payload_length = book.dimension - pilot_length
    energy = float(np.vdot(values[:payload_length], values[:payload_length]).real)
    require(energy > 0 and math.isfinite(energy), "Empty/nonfinite pilot payload")
    gain = math.sqrt(rms * rms * payload_length / energy)
    values[:payload_length] *= gain
    values[payload_length:] = rms * pilot_sequence(book, pilot_length)
    return values, {"length": pilot_length, "sequence": "s1-public-pilot-v1", "amplitude": rms, "payload_gain": gain}


def to_pilot_packet(samples, mask, book, pilot):
    values = signal_array(samples, book.dimension)
    observed = observation_mask(mask, book.dimension)
    values[~observed] = 0
    packet = {"format": FORMAT, "codebook": book.spec, "codebook_fingerprint": book.fingerprint,
              "samples": {"real": values.real.tolist(), "imag": values.imag.tolist()},
              "observed_mask": observed.tolist(), "pilot": dict(pilot),
              "phase_reference": "pilot_estimate_required", "time_axis": None, "chip_rate_hz": None,
              "boundary": dict(BOUNDARY)}
    packet["payload_hash"] = digest(packet)
    from_pilot_packet(packet)
    return packet


def from_pilot_packet(packet, expected_book=None):
    require(type(packet) is dict and set(packet) == {"format", "codebook", "codebook_fingerprint", "samples", "observed_mask", "pilot", "phase_reference", "time_axis", "chip_rate_hz", "boundary", "payload_hash"}, "Unsupported pilot packet fields; truth/offset/assignments prohibited")
    require(packet["format"] == FORMAT and packet["payload_hash"] == digest({k:v for k,v in packet.items() if k != "payload_hash"}), "Pilot packet version/hash mismatch")
    spec = packet["codebook"]
    require(type(spec) is dict and set(spec) == {"algorithm", "dimension", "seed", "symbol_serialization", "phase_units"}, "Invalid book")
    book = PhaseCodebook(spec["dimension"], spec["seed"])
    require(spec == book.spec and packet["codebook_fingerprint"] == book.fingerprint, "Codebook mismatch")
    if expected_book is not None:
        require(expected_book.fingerprint == book.fingerprint, "Receiver book mismatch")
    require(packet["boundary"] == BOUNDARY and packet["boundary"]["inference_enabled"] is False and packet["boundary"]["ss_demodulation_implemented"] is False, "Boundary violation")
    require(packet["phase_reference"] == "pilot_estimate_required" and packet["time_axis"] is None and packet["chip_rate_hz"] is None, "Unsupported time/phase conventions")
    arrays = packet["samples"]
    require(type(arrays) is dict and set(arrays) == {"real", "imag"}, "Invalid complex samples")
    for array in arrays.values():
        require(type(array) is list and len(array) == book.dimension and all(type(x) in (int,float) for x in array), "Invalid numeric array")
    values = signal_array(np.asarray(arrays["real"]) + 1j*np.asarray(arrays["imag"]), book.dimension)
    mask = observation_mask(packet["observed_mask"], book.dimension)
    require(np.all(values[~mask] == 0), "Hidden samples must be zero")
    pilot = packet["pilot"]
    require(type(pilot) is dict and set(pilot) == {"length", "sequence", "amplitude", "payload_gain"}, "Invalid pilot contract")
    require(type(pilot["length"]) is int and 16 <= pilot["length"] <= book.dimension // 4 and pilot["sequence"] == "s1-public-pilot-v1", "Unsupported pilot")
    require(all(type(pilot[k]) in (int,float) and math.isfinite(pilot[k]) and pilot[k] > 0 for k in ("amplitude", "payload_gain")), "Invalid pilot scaling")
    return values, mask, book, pilot


def synchronize(packet, *, expected_book=None):
    values, mask, book, pilot = from_pilot_packet(packet, expected_book)
    length = pilot["length"]
    pmask = mask[-length:]
    observed = int(pmask.sum())
    diagnostics = {"status": "abstain", "reason": "insufficient_pilot_observations", "pilot_observed_components": observed,
                   "estimated_phase_rad": None, "pilot_coherence": None, "eligible_for_inference": False,
                   "ss_demodulation_implemented": False, "scope": "global_phase_only"}
    payload_mask = mask.copy()
    payload_mask[-length:] = False
    empty = np.zeros(book.dimension, complex)
    if observed < 16:
        return empty, payload_mask, book, diagnostics
    reference = pilot["amplitude"] * pilot_sequence(book, length)[pmask]
    received = values[-length:][pmask]
    cross = np.vdot(reference, received)
    energy = float(np.vdot(reference, reference).real * np.vdot(received, received).real)
    require(math.isfinite(energy) and np.isfinite(cross), "Pilot correlation overflow")
    coherence = float(abs(cross) / math.sqrt(energy)) if energy > 0 else 0.
    diagnostics["pilot_coherence"] = round(coherence, 8)
    if coherence < .80:
        return empty, payload_mask, book, dict(diagnostics, reason="pilot_coherence_too_low")
    phase = float(np.angle(cross))
    aligned = values * np.exp(-1j * phase) / pilot["payload_gain"]
    aligned[~payload_mask] = 0
    require(np.isfinite(aligned).all(), "Aligned signal overflow")
    return aligned, payload_mask, book, dict(diagnostics, status="aligned", reason="numerical_phase_estimate_only", estimated_phase_rad=round(phase, 10))
