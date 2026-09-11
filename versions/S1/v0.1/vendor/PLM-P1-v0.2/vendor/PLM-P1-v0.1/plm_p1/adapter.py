"""Read-only bridge from the frozen R1/C2 observation contract."""
from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import sys
from .core import symbol, require, digest, validate_frames

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "PLM-R1-v0.1"


def verify_dependency():
    manifest = json.loads((VENDOR / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    errors = []
    for name, expected in manifest["files"].items():
        path = (VENDOR / name).resolve()
        if not path.is_relative_to(VENDOR.resolve()) or not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(name)
    actual = {p.relative_to(VENDOR).as_posix() for p in VENDOR.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    require(actual == set(manifest["files"]) | {"RELEASE_MANIFEST.json"}, "R1 dependency file inventory mismatch")
    require(not errors, "R1 dependency changed: " + ", ".join(errors))
    return {"version": manifest["release"], "verified_files": len(manifest["files"]), "inventory_files": len(actual)}


def r1_module():
    verify_dependency()
    for name, module in list(sys.modules.items()):
        if name == "plm_r1" or name.startswith("plm_r1."):
            require(Path(module.__file__).resolve().is_relative_to(VENDOR.resolve()), "Conflicting R1 module loaded")
    path = str(VENDOR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("plm_r1")


def from_r1_envelope(envelope):
    r1_module()
    validate = importlib.import_module("plm_r1.contract").validate_envelope
    validate(envelope)
    records = []
    doc = envelope["document_id"]
    for observation in envelope["observations"]:
        slots = {
            "predicate": symbol("predicate", observation["predicate"]),
            "polarity": symbol("state", "polarity:" + observation["polarity"]),
            "modality": symbol("state", "modality:" + observation["modality"]),
            "semantic_status": symbol("state", "semantic_status:" + observation["semantic_status"]),
            "applied": symbol("state", "applied:" + str(observation["applied"]).lower()),
        }
        for role in ("subject", "object"):
            if observation[role + "_entity_id"] is not None:
                slots[role] = symbol("entity", observation[role + "_entity_id"], doc)
        if observation.get("target_clause_id"):
            slots["target_clause"] = symbol("clause", observation["target_clause_id"], doc)
        # Null entity roles are not invented, including legacy and revision frames.
        records.append({"document_id": doc, "event_id": observation["frame_id"], "slots": slots,
                        "metadata": {"eligible_for_inference": False, "source": "R1_C2_observation_not_gold",
                                     "source_observation": deepcopy(observation),
                                     "source_envelope_hash": digest(envelope),
                                     "evidence_ids": deepcopy(observation["evidence_ids"])}})
    validate_frames(records)
    return records


def source_refs(frames):
    validate_frames(frames)
    return [{"document_id": f["document_id"], "event_id": f["event_id"], "source_record_hash": digest(f)} for f in frames]
