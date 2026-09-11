"""Local packaging QA; generates indexes, never changes frozen releases."""
import ast
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs" / "L1-review"


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(value)


coverage = json.loads((BUNDLE / "audit" / "RELEASE_COVERAGE.json").read_text(encoding="utf-8"))
lines = ["# リリース原本と結果の索引\n\n", "各版の原本は下記のディレクトリです。vendorも含め、元の単独配布物とファイル数・全ファイルSHA256を照合しています。\n\n"]
for row in coverage:
    name = row["version"]
    rel = row["canonical_directory"]
    root = BUNDLE / rel
    lines += [f"## {name}\n\n", f"- [README]({rel}/README.md)\n", f"- [全件結果JSON]({rel}/results/EVALUATION.json)\n",
              f"- [受入判断]({rel}/results/RELEASE_DECISION.md)\n", f"- [元の配布検証](release_verification/{name}-VERIFICATION.json)\n",
              f"- [全コードMarkdown](code/{name}-ALL-CODE.md)\n", f"- [全資料Markdown](reports/{name}-ALL-DOCUMENTS.md)\n",
              f"- 原本ファイル数（vendor含む）：{row['files_including_vendor']}\n", f"- 元ZIP SHA256：`{row['original_archive_sha256']}`\n\n"]
write(BUNDLE / "RELEASE_INDEX.md", "".join(lines))
shutil.copytree(ROOT / "work" / "l1-review-check", BUNDLE / "review_verification")
shutil.copyfile(ROOT / "work" / "build_plm_l1_review.py", BUNDLE / "tools" / "build_plm_l1_review.py")
code_index = json.loads((BUNDLE / "audit" / "CODE_INDEX.json").read_text(encoding="utf-8"))
for row in code_index:
    p = BUNDLE / row["path"]
    if hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]:
        raise ValueError("Code export source mismatch")
    if p.suffix == ".py":
        ast.parse(p.read_text(encoding="utf-8-sig"))
# Detect authored-doc dangling links, ignoring fenced code blocks and references
# that are intentionally written as plain code paths in quoted original docs.
authored = ["README.md", "PLM-L1_TECHNICAL_HANDOFF.md", "CLAUDE_REVIEW_REQUEST.md", "CODE_AND_DOCUMENTS.md", "RELEASE_INDEX.md"]
links = 0
for name in authored:
    content = (BUNDLE / name).read_text(encoding="utf-8")
    if "\ufffd" in content:
        raise ValueError(f"Replacement character in {name}")
    stripped = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", content, flags=re.M | re.S)
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", stripped):
        if target.startswith(("http:", "https:", "#")):
            continue
        path = BUNDLE / target.split("#", 1)[0]
        if not path.exists() and target != "PACKAGING_VERIFICATION.md":
            raise ValueError(f"Missing link in {name}: {target}")
        links += 1
totals = collections.Counter()
for row in code_index:
    totals[row["version"]] += row["lines"]
report = {"status": "passed", "authored_documents_checked": authored, "local_links_checked": links,
          "pending_before_pack": ["PACKAGING_VERIFICATION.md"], "code_export_files": len(code_index),
          "code_export_lines_including_requirements_and_per_version_copies": sum(totals.values()),
          "main_markdown_characters": len((BUNDLE / "PLM-L1_TECHNICAL_HANDOFF.md").read_text(encoding="utf-8")),
          "all_exported_python_parses": True, "review_copy_tests": 381, "review_copy_acceptance_checks": 364,
          "full_numeric_evaluation_rerun_this_turn": False}
write(BUNDLE / "audit" / "DOCUMENT_QA.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False))
