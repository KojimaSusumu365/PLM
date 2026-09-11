"""Source freezing, preservation checks, demos and additive ZIP release."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from plm_l1_v02.compat import ROOT, VENDOR, digest, generator
from plm_l1_v02.runtime import PairReader
from plm_l1_v02.bridge import generate, translate


def source_files():
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".md", ".txt")]
    for name in ("plm_l1_v02", "tests", "data", "evaluation", "vendor"):
        files.extend(p for p in (ROOT / name).rglob("*") if p.is_file())
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix != ".pyc")


def hashes(files, base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("baseline", "check-baseline", "freeze", "demo", "pack"))
    args = parser.parse_args()
    if args.command in ("baseline", "check-baseline"):
        files = []
        for name in ("PLM-L1-v0.1", "PLM-P1-v0.2", "PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent / name).rglob("*") if p.is_file())
            files.append(ROOT.parent / (name + ".zip"))
        manifest = {"files": hashes(files, ROOT.parent)}
        path = ROOT / "verification" / "PRESERVED_BASELINE.json"
        if args.command == "baseline":
            write_new(path, manifest)
        elif manifest != json.loads(path.read_text(encoding="utf-8")):
            raise ValueError("existing release changed")
        original = ROOT.parent / "PLM-L1-v0.1"
        a = hashes([p for p in original.rglob("*") if p.is_file()], original)
        b = hashes([p for p in VENDOR.rglob("*") if p.is_file()], VENDOR)
        if a != b:
            raise ValueError("v0.1 vendored copy changed")
        print(json.dumps({"status": "recorded" if args.command == "baseline" else "unchanged", "preserved_files": len(files), "vendor_files": len(a)}))
    elif args.command == "freeze":
        manifest = {"schema": "plm-l1-v02-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write_new(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif args.command == "demo":
        reader = PairReader.load(ROOT / "results" / "reader")
        frozen = generator()
        texts = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けなかったら。", "太郎は花子を助けた。"]
        rows = []
        for text in texts:
            read = reader.read(text)
            row = {"input": text, "status": read["status"], "reason": read["reason"]}
            if read["status"] == "read":
                row["recovered"] = reader.recover(read["packet"])
                row["generated"] = generate(reader, read["packet"], frozen)
                if not rows:
                    write_new(ROOT / "examples" / "MEANING_PACKET.json", read["packet"])
                    write_new(ROOT / "examples" / "LEGACY_GENERATOR_PACKET.json", translate(reader, read["packet"], frozen)["packet"])
            rows.append(row)
        write_new(ROOT / "examples" / "ROUNDTRIPS.json", {"audience": "human/evaluator only; never a generator input", "demos": rows})
    else:
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts)
        write_new(ROOT / "RELEASE_MANIFEST.json", {"schema": "plm-l1-v02-release-v1", "files": hashes(files, ROOT)})
        archive = ROOT.parent / "PLM-L1-v0.2.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with (ROOT.parent / "PLM-L1-v0.2.sha256").open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": checksum, "files": len(files) + 1}))


if __name__ == "__main__":
    main()
