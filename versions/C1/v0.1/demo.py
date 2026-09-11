from __future__ import annotations

import argparse
import json
from pathlib import Path

from plm_c1 import PLMC1Engine


def render_demo():
    engine = PLMC1Engine()
    cases = {
        "same_source_correction": ("犬だと思ったが、実際は猫だった", "entity"),
        "cross_source_correction": (["犬だ", "犬らしい", "訂正すると猫だった"], "entity"),
        "long_negation": ("It is not really very clearly a dog.", "entity"),
        "clause_local_context": ("The bank was discussed while water spilled from a glass.", "place"),
        "isolated_instances": (["I visited a bank.", "Later I crossed a river."], "place"),
        "unseen_correction_marker_failure": ("Initially it was identified as a dog; later it was confirmed to be a cat.", "entity"),
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
            "evidence": [
                evidence for evidence in result["evidence"]
                if engine.concepts[evidence["concept"]]["domain"] == domain
            ],
            "diagnostics": result["diagnostics"],
        }
        sections.append(f"=== {name} ===\n{json.dumps(compact, ensure_ascii=False, indent=2)}")
    return "\n\n".join(sections) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Run PLM-C1 v0.1 operation demos.")
    parser.add_argument("--out", help="Optional UTF-8 output file.")
    args = parser.parse_args()
    output = render_demo()
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
