"""Additive source freezing, preservation checks, demo and ZIP release."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from evaluate import ROOT, source_files
from plm_l1_v03.algebra import digest
from plm_l1_v03.runtime import Writer
from plm_l1_v03.bridge import fixed_reader, translate, VENDOR


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
        manifest = {"schema": "plm-l1-v03-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif command == "check-baseline":
        files = []
        for name in ("PLM-L1-v0.1", "PLM-L1-v0.2", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        baseline = json.loads((ROOT / "verification" / "PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        if hashes(files, ROOT.parent) != baseline:
            raise ValueError("old release changed")
        source = ROOT.parent / "PLM-L1-v0.2"
        if hashes([p for p in source.rglob("*") if p.is_file()], source) != hashes([p for p in VENDOR.rglob("*") if p.is_file()], VENDOR):
            raise ValueError("vendored v0.2 changed")
        print(json.dumps({"status": "unchanged", "preserved_files": len(files), "vendor_files": len(list(p for p in VENDOR.rglob("*") if p.is_file()))}))
    elif command == "demo":
        writer = Writer.load(ROOT / "results" / "writer")
        reader = fixed_reader()
        rows = []
        for text in ("太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。", "太郎は花子を助けた。"):
            read = reader.read(text)
            row = {"input": text, "read_status": read["status"], "reason": read["reason"]}
            if read["status"] == "read":
                packet = translate(reader, read["packet"], writer)["packet"]
                row["meaning"] = writer.recover(packet)["meaning"]
                row["generated"] = {goal: writer.generate(packet, goal) for goal in ("subject", "object")}
                if not rows:
                    write(ROOT / "examples" / "MEANING.json", row["meaning"])
                    write(ROOT / "examples" / "WRITER_MEANING_PACKET.json", packet)
            rows.append(row)
        write(ROOT / "examples" / "ROUNDTRIPS.json", {"scope": "Human/evaluator only, not input to generator", "demos": rows})
    else:
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts)
        write(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v03-release-v1", "files": hashes(files, ROOT)})
        archive = ROOT.parent / "PLM-L1-v0.3.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with (ROOT.parent / "PLM-L1-v0.3.sha256").open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "files": len(files) + 1, "sha256": checksum}))


if __name__ == "__main__":
    main()
