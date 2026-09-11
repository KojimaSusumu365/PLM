from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from plm_c1 import PLMC1Engine


def render_demo():
    engine = PLMC1Engine()
    cases = {
        "same_source_correction": ("犬だと思ったが、実際は猫だった", "entity"),
        "cross_source_correction": (["犬だ", "犬らしい", "訂正すると猫だった"], "entity"),
        "double_negation": ("It is not impossible that this is a dog.", "entity"),
        "hypothetical_relation": ("If there were water, the bank would flood.", "place"),
        "non_spatial_relation": ("The bank published a water policy.", "place"),
        "plural_morphology": ("The bank stopped opening accounts.", "place"),
        "target_isolation": (["I opened an account at a bank.", "Afterward I walked along a river bank."], "place"),
        "known_limit_irregular_plural": ("The puppies were asleep.", "entity"),
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
    parser = argparse.ArgumentParser(description="Run PLM-C1 v0.2 operation demos.")
    parser.add_argument("--out", help="Optional UTF-8 output file.")
    args = parser.parse_args()
    output = render_demo()
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
