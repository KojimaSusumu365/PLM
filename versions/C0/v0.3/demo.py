from __future__ import annotations

import argparse
import json
from pathlib import Path

from plm_c0 import PLMC0Engine


def render_demo():
    engine = PLMC0Engine()
    cases = {
        "multi_paraphrase_consensus": [
            "犬が吠えている",
            "ワンちゃんがキャンキャン鳴いている",
            "イヌが声を出している",
            "dog is barking",
        ],
        "negation": "犬ではなく猫だった",
        "generic_only": "動物が吠えている",
        "financial_bank": "I opened a bank account for my money.",
        "river_bank": "We sat on the river bank near the water.",
        "ascii_boundary_hard_negative": "The hotdog stand closed.",
    }
    sections = []
    for name, value in cases.items():
        result = engine.analyze(value)
        compact = {
            "version": result["version"],
            "inputs": result["inputs"],
            "selections": result["selections"],
            "ranking": {domain: rows[:4] for domain, rows in result["ranking"].items()},
            "diagnostics": result["diagnostics"],
        }
        sections.append(f"=== {name} ===\n{json.dumps(compact, ensure_ascii=False, indent=2)}")
    return "\n\n".join(sections) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Run the PLM-C0 v0.3 demonstration cases.")
    parser.add_argument("--out", help="Optional UTF-8 output file.")
    args = parser.parse_args()
    output = render_demo()
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
