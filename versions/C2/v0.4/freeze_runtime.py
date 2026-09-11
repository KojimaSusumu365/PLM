"""Freeze all implementation, evaluation, test, schema and data dependencies."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json


def tracked_files(root):
    paths = list(root.glob("*.py")) + list(root.glob("*SCHEMA.json"))
    for folder in root.iterdir():
        if folder.is_dir() and (folder.name.startswith("plm_") or folder.name == "tests"):
            paths.extend(folder.rglob("*.py"))
    paths.extend((root / "data").glob("*.json"))
    return sorted(set(paths))


def main():
    root = Path(__file__).resolve().parent
    output = root / "FREEZE_MANIFEST.json"
    if output.exists():
        raise SystemExit("Freeze manifest already exists; preserving recorded experimental boundary.")
    manifest = {"version": "PLM-C2 v0.4", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "all runtime modules including inherited versions, tests, evaluators, schemas and every data split",
                "files": {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest() for p in tracked_files(root)}}
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(manifest['files'])} files.")


if __name__ == "__main__":
    main()
