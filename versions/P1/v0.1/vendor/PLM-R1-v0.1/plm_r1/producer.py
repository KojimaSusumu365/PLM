"""Adapter to the byte-preserved, bundled C2 v0.4 dependency."""
import importlib
import json
from hashlib import sha256
from pathlib import Path
import sys

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "PLM-C2-v0.4"


def verify_dependency():
    manifest = json.loads((VENDOR / "FREEZE_MANIFEST.json").read_text(encoding="utf-8"))
    errors = []
    for name, digest in manifest["files"].items():
        path = (VENDOR / name).resolve()
        if not path.is_relative_to(VENDOR.resolve()) or not path.is_file():
            errors.append(name)
        elif sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(name)
    if errors:
        raise ValueError("C2 frozen dependency mismatch: " + ", ".join(errors))
    return {"version": manifest["version"], "verified_files": len(manifest["files"])}


def _module():
    # Fail closed if a host program has loaded another version under these names.
    for name, module in list(sys.modules.items()):
        if name.startswith(("plm_c0", "plm_c1", "plm_c2")) and getattr(module, "__file__", None):
            if not Path(module.__file__).resolve().is_relative_to(VENDOR.resolve()):
                raise ValueError("Conflicting C2 module already loaded: " + name)
    verify_dependency()
    vendor_path = str(VENDOR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
    return importlib.import_module("plm_c2")


def analyze(inputs):
    if not (isinstance(inputs, str) or
            isinstance(inputs, list) and all(isinstance(t, str) for t in inputs)):
        raise ValueError("inputs must be a string or list of strings")
    return _module().PLMC2Engine().analyze(inputs)


def export_observations(analysis):
    return _module().export_r1_observations(analysis)
