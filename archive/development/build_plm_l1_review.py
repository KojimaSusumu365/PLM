"""Assemble an additive review packet; never edit historical releases."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
NAME = "PLM-L1-Claude-Review-2026-09-07"
BUNDLE = OUT / "L1-review"
STATE = ROOT / "work" / "plm_review_build_state.json"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def files(path):
    return sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def put_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def put_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise ValueError(f"Refusing overwrite: {dest}")
    shutil.copyfile(source, dest)
    if sha(source) != sha(dest):
        raise ValueError(f"Copy mismatch: {source}")


def prepare():
    if BUNDLE.exists() or STATE.exists():
        raise ValueError("Fresh bundle and state paths required")
    BUNDLE.mkdir(parents=True)
    baseline = {}

    def remember(path):
        key = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        baseline[key] = {"sha256": sha(path), "bytes": path.stat().st_size}

    latest = OUT / "PLM-L1-v0.7"
    for p in files(latest):
        remember(p)
        copy(p, BUNDLE / latest.name / p.relative_to(latest))
    canonical = {}
    location = Path(latest.name)
    for version in range(7, 0, -1):
        canonical[version] = location
        if version > 1:
            location = location / "vendor" / f"PLM-L1-v0.{version - 1}"

    coverage, code_index, source_listing, report_listing = [], [], [], []
    for version in range(1, 8):
        name = f"PLM-L1-v0.{version}"
        original = OUT / name
        bundled = BUNDLE / canonical[version]
        orig_map = {p.relative_to(original).as_posix(): sha(p) for p in files(original)}
        bundle_map = {p.relative_to(bundled).as_posix(): sha(p) for p in files(bundled)}
        if orig_map != bundle_map:
            raise ValueError(f"Recursive vendor is not exact original: {name}")
        for p in files(original):
            remember(p)
        archive = OUT / (name + ".zip")
        remember(archive)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError(f"Bad original archive: {archive}")
            archived = {i.filename.removeprefix(name + "/"): hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir()}
            if archived != orig_map:
                raise ValueError(f"Original zip/content disagreement: {name}")
        check = OUT / (name + ".sha256")
        if check.read_text(encoding="utf-8").split()[0] != sha(archive):
            raise ValueError("Original archive SHA256 mismatch")
        for suffix in (".sha256", "-VERIFICATION.md", "-VERIFICATION.json"):
            p = OUT / (name + suffix)
            remember(p)
            copy(p, BUNDLE / "release_verification" / p.name)
        verification = json.loads((OUT / (name + "-VERIFICATION.json")).read_text(encoding="utf-8"))
        coverage.append({"version": name, "canonical_directory": canonical[version].as_posix(), "files_including_vendor": len(orig_map),
                         "original_archive_bytes": archive.stat().st_size, "original_archive_sha256": sha(archive),
                         "original_zip_crc_and_content_checked": True, "recursive_vendor_equals_original": True,
                         "original_zip_container_included": False, "all_original_file_bytes_included": True,
                         "release_verification": verification})
        primary = [p for p in files(original) if "vendor" not in p.relative_to(original).parts]
        code = [p for p in primary if p.suffix in (".py", ".ps1", ".sh") or p.name == "requirements.txt"]
        parts = [f"# {name} 全コード（当該版直下・vendor重複除外）\n\n",
                 "原本はバイト保持されています。本書は閲覧用の全文転記で、改行表現をMarkdown向けに正規化します。実行には原本を使ってください。旧版のコードは各版の別ファイルにあります。\n\n"]
        for p in code:
            rel = (canonical[version] / p.relative_to(original)).as_posix()
            content = p.read_text(encoding="utf-8-sig")
            language = "python" if p.suffix == ".py" else "text"
            parts += [f"## `{p.relative_to(original).as_posix()}`\n\n原本: `{rel}`  \nSHA256: `{sha(p)}`\n\n", f"````{language}\n{content.rstrip()}\n````\n\n"]
            symbols = []
            if p.suffix == ".py":
                tree = ast.parse(content)
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbols.append({"name": node.name, "line": node.lineno, "kind": type(node).__name__})
                        if isinstance(node, ast.ClassDef):
                            symbols.extend({"name": node.name + "." + sub.name, "line": sub.lineno, "kind": type(sub).__name__}
                                           for sub in node.body if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)))
            code_index.append({"version": name, "path": rel, "sha256": sha(p), "lines": len(content.splitlines()), "symbols": symbols})
        code_file = f"code/{name}-ALL-CODE.md"
        put_text(BUNDLE / code_file, "".join(parts))
        source_listing.append(f"- [{name} 全コード]({code_file}) — {len(code)}ファイル。\n")
        md_files = [p for p in primary if p.suffix.lower() == ".md"]
        parts = [f"# {name} 全Markdown資料（vendor重複除外）\n\n", "原文を変更せず閲覧用に転記。原文中の相対パスは各資料の元ディレクトリを基準に読みます。過去版の将来計画は当時の記録であり、最新の実装状態や今回の作業指示ではありません。\n\n"]
        for p in md_files:
            rel = (canonical[version] / p.relative_to(original)).as_posix()
            content = p.read_text(encoding="utf-8-sig")
            parts += [f"## 原本 `{p.relative_to(original).as_posix()}`\n\n保管先: `{rel}`  \nSHA256: `{sha(p)}`\n\n", f"````markdown\n{content.rstrip()}\n````\n\n"]
        md_file = f"reports/{name}-ALL-DOCUMENTS.md"
        put_text(BUNDLE / md_file, "".join(parts))
        report_listing.append(f"- [{name} 全Markdown資料]({md_file}) — {len(md_files)}資料。\n")
    put_json(BUNDLE / "audit" / "RELEASE_COVERAGE.json", coverage)
    put_json(BUNDLE / "audit" / "CODE_INDEX.json", code_index)
    put_text(BUNDLE / "CODE_AND_DOCUMENTS.md", "# 全コード・資料の閲覧入口\n\n" + "".join(source_listing) + "\n" + "".join(report_listing)
             + "\nモデル重み、全件JSON、データ、プロトコル、テスト・検証ログは原本ツリーに完全収録。位置は [リリース対応表](audit/RELEASE_COVERAGE.json) を参照。\n")
    direction = OUT / "PLM-SS-LANGUAGE-DIRECTION.md"
    remember(direction)
    copy(direction, BUNDLE / direction.name)

    backgrounds = []
    for archive in sorted(OUT.glob("PLM-*.zip")):
        if archive.name.startswith("PLM-L1-"):
            continue
        remember(archive)
        copy(archive, BUNDLE / "background" / "archives" / archive.name)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:
                raise ValueError(f"Bad background archive: {archive}")
        backgrounds.append({"path": "background/archives/" + archive.name, "sha256": sha(archive), "bytes": archive.stat().st_size})
        source = OUT / archive.stem
        for p in files(source):
            if p.suffix.lower() == ".md" and "vendor" not in p.relative_to(source).parts:
                remember(p)
                copy(p, BUNDLE / "background" / "documents" / source.name / p.relative_to(source))
        for suffix in (".sha256", "-VERIFICATION.md", "-VERIFICATION.json"):
            p = OUT / (archive.stem + suffix)
            if p.exists():
                remember(p)
                copy(p, BUNDLE / "background" / "verification" / p.name)
    original_attachment = Path("C:/Users/kojim/Downloads/PLM-C0-v0.1.zip")
    if original_attachment.is_file():
        remember(original_attachment)
        copy(original_attachment, BUNDLE / "background" / "archives" / original_attachment.name)
        with zipfile.ZipFile(original_attachment) as z:
            if z.testzip() is not None:
                raise ValueError("Bad initial attachment")
        backgrounds.append({"path": "background/archives/" + original_attachment.name, "sha256": sha(original_attachment), "bytes": original_attachment.stat().st_size, "origin": "user_named_attachment"})
    put_json(BUNDLE / "audit" / "BACKGROUND_ARCHIVES.json", backgrounds)

    # Account for all L1-labelled local development/evaluation/replay evidence.
    # A mapping preserves all source identities; identical bytes are stored once.
    by_hash = {}
    for p in files(BUNDLE):
        by_hash.setdefault(sha(p), p.relative_to(BUNDLE).as_posix())
    work_roots = sorted(p for p in (ROOT / "work").iterdir() if p.name.lower().startswith(("plm-l1-", "prepare-l1-")))
    evidence = []
    added = 0
    for entry in work_roots:
        for p in files(entry) if entry.is_dir() else [entry]:
            remember(p)
            h = sha(p)
            origin = p.relative_to(ROOT / "work").as_posix()
            duplicate = h in by_hash
            if not duplicate:
                dest = BUNDLE / "development_evidence" / origin
                copy(p, dest)
                by_hash[h] = dest.relative_to(BUNDLE).as_posix()
                added += 1
            evidence.append({"original_work_path": origin, "stored_path": by_hash[h], "sha256": h,
                             "bytes": p.stat().st_size, "deduplicated": duplicate,
                             "status": "historical_development_or_replay_not_new_independent_evaluation"})
    put_json(BUNDLE / "audit" / "WORK_EVIDENCE_MAP.json", evidence)
    put_json(BUNDLE / "audit" / "ORIGINAL_SOURCE_MANIFEST.json", baseline)
    import numpy as np
    state = {"bundle": str(BUNDLE), "baseline": baseline, "coverage": coverage,
             "work_evidence_files": len(evidence), "new_unique_work_files": added,
             "background_archives": len(backgrounds), "python": sys.version, "numpy": np.__version__,
             "platform": platform.platform(), "full_numeric_evaluation_rerun_in_this_packaging_task": False}
    put_json(STATE, state)
    print(json.dumps({k: state[k] for k in ("bundle", "work_evidence_files", "new_unique_work_files", "background_archives", "python", "numpy")}, ensure_ascii=False))
    print(json.dumps({"files": len(files(BUNDLE)), "bytes": sum(p.stat().st_size for p in files(BUNDLE))}))


def preserve():
    state = json.loads(STATE.read_text(encoding="utf-8"))
    for name, expected in state["baseline"].items():
        path = Path(name) if Path(name).is_absolute() else ROOT / name
        if not path.is_file() or path.stat().st_size != expected["bytes"] or sha(path) != expected["sha256"]:
            raise ValueError(f"Original changed: {path}")
    return state


def pack():
    state = preserve()
    check = json.loads((BUNDLE / "review_verification" / "VERIFICATION.json").read_text(encoding="utf-8"))
    if check["status"] != "passed" or sum(check["test_counts"].values()) != 381 or check["acceptance_checks"] != 364:
        raise ValueError("Fresh review-copy verification not complete")
    put_json(BUNDLE / "audit" / "PRESERVATION_CHECK.json", {"status": "passed", "original_files_checked": len(state["baseline"]), "method": "size and SHA256 unchanged before packaging"})
    manifest = {p.relative_to(BUNDLE).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in files(BUNDLE)}
    put_json(BUNDLE / "BUNDLE_MANIFEST.json", {"schema": "plm-l1-review-bundle-v1", "self_excluded": ["BUNDLE_MANIFEST.json"], "files": manifest})
    archive = OUT / (NAME + ".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files(BUNDLE):
            z.write(p, BUNDLE.name + "/" + p.relative_to(BUNDLE).as_posix())
    h = sha(archive)
    put_text(OUT / (NAME + ".sha256"), h + "  " + archive.name + "\n")
    print(json.dumps({"archive": str(archive), "sha256": h, "bytes": archive.stat().st_size, "files": len(files(BUNDLE))}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "preserve", "pack"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "pack":
        pack()
    else:
        state = preserve()
        print(json.dumps({"status": "unchanged", "files": len(state["baseline"])}))
