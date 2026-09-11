"""Freeze sources before evaluation. Artifacts/results are covered at packaging."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "SOURCE_MANIFEST.json"


def snapshot():
    files = list(ROOT.glob("*.py")) + list(ROOT.glob("*.md")) + [ROOT / "requirements.txt", ROOT / "S1_PACKET_SCHEMA.json"]
    for name in ("plm_p1", "tests", "evaluation", "vendor"):
        files.extend((ROOT / name).rglob("*"))
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files)) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def verify():
    expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    actual = snapshot()
    differences = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
    return {"valid": not differences, "verified_files": len(actual), "differences": differences}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    if args.create:
        with MANIFEST.open("x", encoding="utf-8") as stream:
            json.dump({"version": "PLM-P1 v0.1", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                       "scope": "runtime, tests, docs, schema, protocol, dependency; frozen before evaluation seeds",
                       "files": snapshot()}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    result = verify()
    print(json.dumps(result))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
