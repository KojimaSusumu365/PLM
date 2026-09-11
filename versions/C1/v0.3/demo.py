from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from plm_c1 import PLMC1Engine


def render_demo():
    engine = PLMC1Engine()
    cases = {
        "revision_retraction": ("The dog classification was ruled out; the cat classification remained.", "entity"),
        "japanese_retraction": ("犬という判定を撤回、猫を確認済み", "entity"),
        "irregular_plural": ("Several puppies were asleep.", "entity"),
        "past_tense": ("The animal barked loudly.", "action"),
        "double_negation": ("It is not impossible that this is a dog.", "entity"),
        "event_identity": (["A dog was logged.", "Another instance contains a cat."], "entity"),
        "approved_compound": ("The bank runs along the riverfront.", "place"),
        "open_set_confidence": ("The quokka rested quietly.", "entity"),
        "known_limit_closed_compound": ("They rested on the riverbank.", "place"),
    }
    sections = []
    for name, (inputs, domain) in cases.items():
        result = engine.analyze(inputs)
        compact = {
            "version": result["version"],
            "inputs": result["inputs"],
            "domain": domain,
            "selection": result["selections"][domain],
            "clauses": result["clauses"],
            "operations": result["operations"],
            "relations": result["relations"],
            "targets": result["targets"],
            "normalizations": result["normalizations"],
            "evidence": [
                evidence for evidence in result["evidence"]
                if engine.concepts[evidence["concept"]]["domain"] == domain
            ],
            "diagnostics": result["diagnostics"],
        }
        sections.append(f"=== {name} ===\n{json.dumps(compact, ensure_ascii=False, indent=2)}")
    return "\n\n".join(sections) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run PLM-C1 v0.3 operation demos.")
    parser.add_argument("--out", help="Optional UTF-8 output file.")
    args = parser.parse_args()
    output = render_demo()
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
