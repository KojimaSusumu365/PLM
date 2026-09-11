"""Additive source freezing, prior-release preservation, examples and ZIP."""
import argparse
import hashlib
import json
import zipfile
from evaluate import ROOT, source_files, verify_freeze
from evaluation_support import V05
from plm_l1_v06.algebra import digest
from plm_l1_v06.runtime import Model


def hashes(files, root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "check-baseline", "demo", "pack"))
    command = parser.parse_args().command
    if command == "freeze":
        manifest = {"schema": "plm-l1-v06-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif command == "check-baseline":
        files = []
        for name in ("PLM-L1-v0.1", "PLM-L1-v0.2", "PLM-L1-v0.3", "PLM-L1-v0.4", "PLM-L1-v0.5", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        baseline = json.loads((ROOT / "verification" / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        if hashes(files, ROOT.parent) != baseline:
            raise ValueError("old release changed")
        source = ROOT.parent / "PLM-L1-v0.5"
        vendor_files = [p for p in V05.rglob("*") if p.is_file()]
        if hashes([p for p in source.rglob("*") if p.is_file()], source) != hashes(vendor_files, V05):
            raise ValueError("vendored v0.5 changed")
        print(json.dumps({"status": "unchanged", "preserved_files": len(files), "vendor_files": len(vendor_files)}))
    elif command == "demo":
        model = Model.load(ROOT / "results" / "model")
        rows = []
        for text in ("花子を太郎が助けなかった。", "もし花子を太郎が助けなかったら。", "太郎を花子が助けなかった。", "太郎が花子を助けた。", "太郎は花子を助けた。"):
            read = model.read(text)
            row = {"input": text, "read_status": read["status"], "reason": read.get("reason")}
            if read["status"] == "read":
                row["meaning"] = model.recover(read["packet"])["meaning"]
                row["generated"] = {goal: model.generate(read["packet"], goal) for goal in ("subject", "object")}
                if not rows:
                    write(ROOT / "examples" / "MEANING.json", row["meaning"])
                    write(ROOT / "examples" / "MEANING_PACKET.json", read["packet"])
            rows.append(row)
        write(ROOT / "examples" / "ROUNDTRIPS.json", {"scope": "Human/evaluator only; source text is not generator input", "training_excluded_cell": "object_negative", "demos": rows})
    else:
        verify_freeze()
        verification = json.loads((ROOT / "verification" / "REPRODUCIBILITY.json").read_text(encoding="utf-8"))
        if verification["status"] != "passed" or verification["complete_numeric_runs"] != 2:
            raise ValueError("completed reproducibility verification required")
        archive = ROOT.parent / "PLM-L1-v0.6.zip"
        checksum_path = ROOT.parent / "PLM-L1-v0.6.sha256"
        if archive.exists() or checksum_path.exists():
            raise ValueError("release archive already exists")
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0] != "work")
        write(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v06-release-v1", "files": hashes(files, ROOT)})
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with checksum_path.open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(files) + 1, "sha256": checksum}))


if __name__ == "__main__":
    main()
