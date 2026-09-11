from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from plm_c2 import PLMC2Engine, export_r1_observations


def render_demo():
    engine = PLMC2Engine()
    cases = {
        "generalized_revision": ("Originally marked dog: reclassified as cat.", "entity"),
        "nominal_coreference": (["A dog and a cat were listed.", "The earlier one was selected."], "entity"),
        "bounded_pronoun": (["A cat entered the room.", "It was photographed."], "entity"),
        "plural_reference": (["A dog and a cat entered.", "They were photographed."], "entity"),
        "japanese_correction": ("犬、いや、猫。", "entity"),
        "japanese_reference": (["犬と猫を登録した。", "後者を選んだ。"], "entity"),
        "role_affordance": ("The bank granted aid to a river project.", "place"),
        "passive_agent": ("Aid to a river project was granted by the bank.", "place"),
        "noun_support": ("The bank support structure stands near the river.", "place"),
        "same_concept_distinct_instances": (["A dog and another dog entered.", "It was photographed."], "entity"),
        "passive_role_guard": ("The bank was supported by a river alliance.", "place"),
        "known_gap_reidentified_fixed": ("Originally marked dog: reidentified as cat.", "entity"),
        "empty_not_ready": ("", "entity"),
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
            "relation_frames": result["relation_frames"],
            "relation_contract": result["relation_contract"],
            "mentions": result["mentions"],
            "entities": result["entities"],
            "reference_resolutions": result["reference_resolutions"],
            "semantic_audit": result["semantic_audit"],
            "r1_boundary": result["r1_boundary"],
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
    parser = argparse.ArgumentParser(description="Run PLM-C2 v0.4 semantic-audit demos.")
    parser.add_argument("--out", help="Optional UTF-8 output file.")
    parser.add_argument("--observations-out", help="Optional R1 observation-only JSON sample.")
    args = parser.parse_args()
    output = render_demo()
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    if args.observations_out:
        result = PLMC2Engine().analyze("Grants for a river restoration were awarded by the bank.")
        Path(args.observations_out).write_text(json.dumps(export_r1_observations(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
