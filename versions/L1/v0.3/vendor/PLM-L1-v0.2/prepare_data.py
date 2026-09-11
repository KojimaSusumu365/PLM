"""Dataset-side export ONLY. Old grammar generates fixtures, never learner labels.

The pair learner does not import this module. Trace/order/IDs are discarded.
Old reader_trace/writer_trace are not called, including during export.
"""
import json
from pathlib import Path
from plm_l1_v02.compat import ROOT, generator
from plm_l1.teacher import examples, lexicon


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    for split in ("train", "development", "evaluation"):
        pairs = [{"text": row["text"], "meaning": row["slots"]} for row in examples(split)]
        write_new(ROOT / "data" / (split + ".json"), pairs)
    tokens = []
    for surface, category, value in lexicon():
        if surface == "<EOS>":
            continue
        kind = "entity" if value.startswith("entity:") else "predicate" if value.startswith("predicate:") else "marker"
        tokens.append({"surface": surface, "kind": kind, "value": value if kind != "marker" else None})
    write_new(ROOT / "data" / "lexicon.json", {"tokens": tokens, "slot_candidates": generator().meta["slot_candidates"]})


if __name__ == "__main__":
    main()
