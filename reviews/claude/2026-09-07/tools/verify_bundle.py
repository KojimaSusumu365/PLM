"""Read-only bundle integrity check; optional safe extraction into a fresh path.

This verifies content integrity, not authorship, authenticity or semantic truth.
Python standard library only. It does not execute archived source code.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_relative(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or ":" in value or p.as_posix() != value:
        raise ValueError(f"Unsafe relative path: {value!r}")
    return p


def file_map(root):
    result = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError(f"Unexpected symlink: {p}")
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            # The release CLI intentionally writes experiments under work/.
            # Ignore only work/ owned by a frozen release directory.
            parts = p.relative_to(root).parts
            if any(part == "work" and index and parts[index - 1].startswith("PLM-L1-v0.") for index, part in enumerate(parts)):
                continue
            result[rel] = {"bytes": p.stat().st_size, "sha256": sha(p)}
    return result


def verify_root(root):
    manifest_path = root / "BUNDLE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "plm-l1-review-bundle-v1" or manifest.get("self_excluded") != ["BUNDLE_MANIFEST.json"]:
        raise ValueError("Unexpected bundle manifest")
    expected = manifest["files"]
    for name in expected:
        safe_relative(name)
    if len({x.casefold() for x in expected}) != len(expected):
        raise ValueError("Case-insensitive path collision")
    actual = file_map(root)
    actual.pop("BUNDLE_MANIFEST.json")
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])
        raise ValueError(json.dumps({"missing": missing, "extra": extra, "changed": changed}))
    coverage = json.loads((root / "audit" / "RELEASE_COVERAGE.json").read_text(encoding="utf-8"))
    for row in coverage:
        relative = safe_relative(row["canonical_directory"]).as_posix()
        count = sum(name.startswith(relative + "/") for name in expected)
        if count != row["files_including_vendor"]:
            raise ValueError(f"Release coverage count mismatch: {row['version']}")
    evidence = json.loads((root / "audit" / "WORK_EVIDENCE_MAP.json").read_text(encoding="utf-8"))
    for row in evidence:
        name = safe_relative(row["stored_path"]).as_posix()
        if expected.get(name) != {"sha256": row["sha256"], "bytes": row["bytes"]}:
            raise ValueError(f"Historical work evidence mismatch: {row['original_work_path']}")
    return {"status": "passed", "files_including_manifest": len(expected) + 1,
            "payload_bytes_excluding_manifest": sum(v["bytes"] for v in expected.values()),
            "release_versions": len(coverage), "historical_work_files_mapped": len(evidence),
            "authentication_or_semantic_truth_verified": False}


def inspect_archive(archive):
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        names = []
        for item in infos:
            safe_relative(item.filename.rstrip("/"))
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Archive symlink prohibited")
            if item.flag_bits & 1:
                raise ValueError("Encrypted archive entry prohibited")
            names.append(item.filename)
        if len(names) != len(set(names)) or len(names) != len({n.casefold() for n in names}):
            raise ValueError("Duplicate archive paths")
        if {PurePosixPath(n).parts[0] for n in names} != {"L1-review"}:
            raise ValueError("Unexpected archive root")
        if z.testzip() is not None:
            raise ValueError("Archive CRC failure")
        manifest = json.loads(z.read("L1-review/BUNDLE_MANIFEST.json"))
        expected = manifest["files"]
        actual = {}
        for item in infos:
            if item.is_dir() or item.filename == "L1-review/BUNDLE_MANIFEST.json":
                continue
            with z.open(item) as stream:
                h = hashlib.file_digest(stream, "sha256").hexdigest()
            actual[item.filename.removeprefix("L1-review/")] = {"sha256": h, "bytes": item.file_size}
        if actual != expected:
            raise ValueError("Archived bytes do not match bundle manifest")
        return {"status": "passed", "sha256": sha(archive), "bytes": archive.stat().st_size, "files": len(actual) + 1}


def extract_fresh(archive, destination):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Extraction requires a new, non-existent directory")
    # Validate all archive members before creating anything.
    inspect_archive(archive)
    with zipfile.ZipFile(archive) as z:
        targets = []
        for info in z.infolist():
            rel = safe_relative(info.filename.rstrip("/"))
            target = destination.joinpath(*rel.parts).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Archive extraction escaped target directory")
            targets.append((info, target))
        destination.mkdir(parents=True)
        for info, target in targets:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
    return destination / "L1-review"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--extract-to", type=Path)
    args = parser.parse_args()
    if args.extract_to and not args.archive:
        parser.error("--extract-to requires --archive")
    report = {"root": verify_root(args.root.resolve())}
    if args.archive:
        report["archive"] = inspect_archive(args.archive.resolve())
    if args.extract_to:
        target = extract_fresh(args.archive.resolve(), args.extract_to)
        report["extracted"] = verify_root(target)
        report["extracted_root"] = str(target)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
