"""Record/verify local release-source hashes; not a publisher signature."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "SOURCE_MANIFEST.json"


def paths():
    candidates = list(ROOT.glob("*.py")) + list(ROOT.glob("*.md"))
    for folder in ("plm_r1", "tests", "evaluation", "vendor"):
        candidates.extend((ROOT / folder).rglob("*"))
    return sorted({p for p in candidates if p.is_file() and "__pycache__" not in p.parts
                   and p.suffix != ".pyc" and p.name != "INDEPENDENT_EVALUATION_STATUS.json"})


def snapshot():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in paths()}


def verify():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = snapshot()
    differences = sorted(k for k in actual.keys() | manifest["files"].keys() if actual.get(k) != manifest["files"].get(k))
    return {"valid": not differences, "verified_files": len(actual), "differences": differences}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true", help="Maintainer action; does not overwrite existing freeze")
    args = parser.parse_args()
    if args.create:
        with MANIFEST.open("x", encoding="utf-8") as stream:
            json.dump({"version": "PLM-R1 v0.1", "scope": "source, tests, protocol, blank templates and unchanged C2 dependency",
                       "independent_semantic_evaluation": "not_performed", "files": snapshot()}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    result = verify()
    print(json.dumps(result))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
