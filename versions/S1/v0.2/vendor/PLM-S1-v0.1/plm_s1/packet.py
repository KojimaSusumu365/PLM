"""Strict new S1 wire contract. No ground truth/channel perturbations are allowed."""
from dataclasses import fields
import math
import numpy as np
from plm_p1.core import PhaseCodebook,digest,require,signal_array,observation_mask
from .link import Link

FORMAT="PLM-S1-chip-observation-packet-v1"
BOUNDARY={"mode":"observe_only","inference_enabled":False,"independent_semantic_validation":"not_performed",
          "ss_demodulation_implemented":True,"implementation_scope":"synthetic_discrete_complex_baseband_only"}


def to_packet(samples,mask,book,link,normalization,*,source_digest):
    y=signal_array(samples,link.frame_length)
    m=observation_mask(mask,link.frame_length)
    y[~m]=0
    packet={"format":FORMAT,"producer_version":"PLM-S1 v0.1","codebook":book.spec,"codebook_fingerprint":book.fingerprint,
            "link":link.spec,"link_fingerprint":link.fingerprint,"normalization":dict(normalization),
            "samples":{"real":y.real.tolist(),"imag":y.imag.tolist()},"observed_mask":m.tolist(),
            "time_axis":{"origin_seconds":0.,"sample_spacing_seconds":1/link.chip_rate_hz,"sample_count":link.frame_length},
            "phase_reference":"pilot_estimation_required","source_digest":source_digest,"boundary":dict(BOUNDARY)}
    packet["payload_hash"]=digest(packet)
    from_packet(packet)
    return packet


def from_packet(packet,*,expected_book=None,expected_link=None):
    require(type(packet) is dict and set(packet)=={"format","producer_version","codebook","codebook_fingerprint","link","link_fingerprint","normalization","samples","observed_mask","time_axis","phase_reference","source_digest","boundary","payload_hash"},"Unsupported packet fields; gold/true offsets/slot assignments prohibited")
    require(packet["format"]==FORMAT and packet["producer_version"]=="PLM-S1 v0.1","Unsupported packet version")
    require(packet["payload_hash"]==digest({k:v for k,v in packet.items() if k!="payload_hash"}),"Checksum mismatch")
    spec=packet["codebook"]
    require(type(spec) is dict and set(spec)=={"algorithm","dimension","seed","symbol_serialization","phase_units"},"Invalid codebook spec")
    book=PhaseCodebook(spec["dimension"],spec["seed"])
    require(spec==book.spec and packet["codebook_fingerprint"]==book.fingerprint,"Codebook mismatch")
    link_spec=packet["link"]
    require(type(link_spec) is dict and set(link_spec)=={f.name for f in fields(Link)},"Invalid link specification")
    link=Link(**link_spec).validate()
    require(book.dimension==link.dimension and packet["link_fingerprint"]==link.fingerprint,"Link mismatch")
    if expected_book is not None: require(book.fingerprint==expected_book.fingerprint,"Pinned receiver codebook mismatch")
    if expected_link is not None: require(link.fingerprint==expected_link.validate().fingerprint,"Pinned receiver link mismatch")
    norm=packet["normalization"]
    require(type(norm) is dict and set(norm)=={"payload_gain","pilot_amplitude","total_tx_energy"},"Invalid normalization")
    require(all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in norm.values()),"Invalid normalization values")
    expected_amplitude=math.sqrt(norm["total_tx_energy"]/(link.payload_length+2*link.pilot_length))
    require(math.isclose(norm["pilot_amplitude"],expected_amplitude,rel_tol=1e-12,abs_tol=0.),"Pilot energy convention mismatch")
    a=packet["samples"]
    require(type(a) is dict and set(a)=={"real","imag"},"Invalid complex arrays")
    for array in a.values():
        require(type(array) is list and len(array)==link.frame_length and all(type(v) in (int,float) for v in array),"Invalid chip array")
    y=signal_array(np.asarray(a["real"])+1j*np.asarray(a["imag"]),link.frame_length)
    m=observation_mask(packet["observed_mask"],link.frame_length)
    require(np.all(y[~m]==0),"Unobserved chips must be zero")
    timing=packet["time_axis"]
    require(type(timing) is dict and set(timing)=={"origin_seconds","sample_spacing_seconds","sample_count"},"Invalid time axis")
    require(type(timing["sample_count"]) is int and timing["sample_count"]==link.frame_length,"Time-axis length mismatch")
    require(type(timing["origin_seconds"]) in (int,float) and timing["origin_seconds"]==0. and type(timing["sample_spacing_seconds"]) in (int,float) and timing["sample_spacing_seconds"]==1/link.chip_rate_hz,"Unsupported capture time convention")
    require(packet["phase_reference"]=="pilot_estimation_required","Invalid phase reference")
    require(packet["boundary"]==BOUNDARY and packet["boundary"]["inference_enabled"] is False and packet["boundary"]["ss_demodulation_implemented"] is True,"Boundary violation")
    source=packet["source_digest"]
    require(type(source) is str and len(source)==64 and all(c in "0123456789abcdef" for c in source),"Invalid source audit digest")
    return y,m,book,link,dict(norm)
