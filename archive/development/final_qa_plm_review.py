"""Final authored-doc/source checks before the immutable outer archive."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs" / "L1-review"
names = ["README.md", "PLM-L1_TECHNICAL_HANDOFF.md", "CLAUDE_REVIEW_REQUEST.md", "CODE_AND_DOCUMENTS.md", "RELEASE_INDEX.md", "PACKAGING_VERIFICATION.md"]
links = []
for name in names:
    content = (BUNDLE / name).read_text(encoding="utf-8")
    if content.count("```") % 2 or "\ufffd" in content:
        raise ValueError(f"Invalid fence or replacement character: {name}")
    stripped = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", content, flags=re.M | re.S)
    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", stripped):
        if target.startswith(("https:", "http:", "#")):
            continue
        p = (BUNDLE / target.split("#", 1)[0]).resolve()
        if not p.is_relative_to(BUNDLE) or not p.exists():
            raise ValueError(f"Broken or escaped authored link: {name}: {target}")
        links.append({"document": name, "target": target})
for p in (BUNDLE / "tools").glob("*.py"):
    ast.parse(p.read_text(encoding="utf-8"))
# Validate that full code exports contain every original body, not excerpts.
code_index = json.loads((BUNDLE / "audit" / "CODE_INDEX.json").read_text(encoding="utf-8"))
for row in code_index:
    body = (BUNDLE / row["path"]).read_text(encoding="utf-8-sig").rstrip()
    export = (BUNDLE / "code" / (row["version"] + "-ALL-CODE.md")).read_text(encoding="utf-8")
    if body not in export or row["sha256"] not in export:
        raise ValueError("Code missing from full export")
v = json.loads((BUNDLE / "review_verification" / "VERIFICATION.json").read_text(encoding="utf-8"))
state = json.loads((ROOT / "work" / "plm_review_build_state.json").read_text(encoding="utf-8"))
report = {"status": "passed", "documents": names, "local_links_checked": len(links), "links": links,
          "all_code_bodies_present": True, "code_files_in_exports": len(code_index), "original_files_in_preservation_baseline": len(state["baseline"]),
          "review_copy_tests": sum(v["test_counts"].values()), "review_copy_acceptance_checks": v["acceptance_checks"],
          "full_numeric_evaluation_rerun": False}
with (BUNDLE / "audit" / "FINAL_DOCUMENT_QA.json").open("x", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps({k: x for k, x in report.items() if k != "links"}, ensure_ascii=False))
