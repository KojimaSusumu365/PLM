"""Reproducible source freeze and additive release packaging; no old release edits."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from plm_l1.algebra import digest
from plm_l1.runtime import Model

ROOT = Path(__file__).resolve().parent
EXCLUDED = {"results", "verification", "examples", "__pycache__"}
MANIFESTS = {"SOURCE_MANIFEST.json", "RELEASE_MANIFEST.json"}


def source_files():
    # Root JSON/NPZ files can be CLI outputs. Source/config files live in the
    # explicit inventories below; generated packets must not invalidate them.
    paths = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py", ".md", ".txt") and p.name not in MANIFESTS]
    for name in ("plm_l1", "tests", "evaluation"):
        paths.extend(p for p in (ROOT / name).rglob("*") if p.is_file())
    return sorted(p for p in paths if "__pycache__" not in p.parts and p.suffix != ".pyc")


def hashes(paths, base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "baseline", "check-baseline", "demo", "pack"))
    args = parser.parse_args()
    if args.command == "freeze":
        manifest = {"schema": "plm-l1-source-freeze-v1", "files": hashes(source_files(), ROOT)}
        write_new(ROOT / "SOURCE_MANIFEST.json", manifest)
        print(json.dumps({"files": len(manifest["files"]), "digest": digest(manifest)}))
    elif args.command in ("baseline", "check-baseline"):
        targets = []
        for name in ("PLM-P1-v0.2", "PLM-S1-v0.2"):
            folder = ROOT.parent / name
            targets += [p for p in folder.rglob("*") if p.is_file()]
            targets += [ROOT.parent / (name + ".zip")]
        snapshot = {"schema": "plm-l1-preserved-releases-v1", "files": hashes(sorted(targets), ROOT.parent)}
        path = ROOT / "verification" / "PRESERVED_BASELINE.json"
        if args.command == "baseline":
            write_new(path, snapshot)
        else:
            if snapshot != json.loads(path.read_text(encoding="utf-8")):
                raise ValueError("preserved release changed")
        print(json.dumps({"status": "unchanged" if args.command == "check-baseline" else "recorded", "files": len(snapshot["files"])}))
    elif args.command == "demo":
        model = Model.load(ROOT / "results" / "model")
        inputs = ["太郎が花子を助けた。", "花子が太郎を助けた。", "太郎が花子を助けなかった。", "もし太郎が花子を助けたら。", "もし太郎が花子を助けなかったら。", "太郎は花子を助けた。"]
        demos = []
        for text in inputs:
            read = model.read(text)
            row = {"input": text, "read_status": read["status"], "reason": read["reason"]}
            if read["status"] == "read":
                row["recovered"] = model.recover(read["packet"])
                row["generated"] = model.generate(read["packet"], "object_first")
                if not demos:
                    write_new(ROOT / "examples" / "MEANING_PACKET.json", read["packet"])
            demos.append(row)
        write_new(ROOT / "examples" / "ROUNDTRIP_DEMOS.json", {"audience": "human/evaluator only; never input to generator", "demos": demos})
    else:
        files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.name != "RELEASE_MANIFEST.json" and "__pycache__" not in p.parts)
        manifest = {"schema": "plm-l1-release-v1", "files": hashes(files, ROOT)}
        write_new(ROOT / "RELEASE_MANIFEST.json", manifest)
        archive = ROOT.parent / "PLM-L1-v0.1.zip"
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
            for path in files + [ROOT / "RELEASE_MANIFEST.json"]:
                stream.write(path, ROOT.name + "/" + path.relative_to(ROOT).as_posix())
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        with (ROOT.parent / "PLM-L1-v0.1.sha256").open("x", encoding="utf-8") as stream:
            stream.write(checksum + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size, "sha256": checksum, "files": len(files) + 1}))


if __name__ == "__main__":
    main()
