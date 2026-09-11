from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from plm_c2 import PLMC2Engine


def render_demo():
    engine = PLMC2Engine()
    cases = {
        "ordered_coreference": (["A dog and a cat were observed.", "The latter was selected."], "entity"),
        "contrastive_correction": ("It was not a dog, rather a cat.", "entity"),
        "structural_revision": ("Originally labeled a dog: revised finding labels it a cat.", "entity"),
        "agentive_affordance": ("The bank sponsored a river cleanup project.", "place"),
        "negated_affordance": ("The bank did not sponsor a river cleanup project.", "place"),
        "calibrated_open_set": ("The marten crossed the clearing.", "entity"),
        "preserved_temporal_identity": (["A dog was examined.", "Subsequently, a cat was examined."], "entity"),
        "known_limit_reclassified": ("Originally marked dog: reclassified as cat.", "entity"),
    }
    sections = []
    for name, (inputs, domain) in cases.items():
        result = engine.analyze(inputs)
        graph = result["claim_graph"]
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
            "event_links": result["event_links"],
            "reference_links": result["reference_links"],
            "claim_graph": {
                "schema_version": graph["schema_version"],
                "node_types": dict(sorted(Counter(node["node_type"] for node in graph["nodes"]).items())),
                "edge_relations": dict(sorted(Counter(edge["relation"] for edge in graph["edges"]).items())),
                "invariants": graph["invariants"],
            },
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
    parser = argparse.ArgumentParser(description="Run PLM-C2 v0.2 discourse-graph demos.")
    parser.add_argument("--out", help="Optional UTF-8 output file.")
    args = parser.parse_args()
    output = render_demo()
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
