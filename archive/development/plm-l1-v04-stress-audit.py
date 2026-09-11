"""Describe the frozen low-dimensional failure without tuning the model."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent / "outputs" / "PLM-L1-v0.4"
sys.path.insert(0, str(ROOT))
from evaluate import verify_freeze, bad_packets
from evaluation_support import INVALID, data, train_for
from plm_l1_v04.training import fit

fixed = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
details = []
for row in fixed["stress"]:
    c = row["counts"]
    if not c["invalid_texts_accepted"] and not c["invalid_packets_generated"] and not sum(v for k,v in c.items() if k.endswith("_wrong")):
        continue
    model = fit(train_for(row["fold"]), data("lexicon"), seed=row["seed"], dimension=row["dimension"])
    assert model.fingerprint == row["fingerprint"]
    texts = []
    for text in INVALID:
        read = model.read(text)
        if read["status"] == "read":
            recovered = model.recover(read["packet"])
            texts.append({"input": text, "status": read["status"], "incorrectly_accepted_meaning": recovered.get("meaning"), "generated_for_audit": model.generate(read["packet"], "object")})
    packets = []
    for i, packet in enumerate(bad_packets(model, data("evaluation")[0]["meaning"])):
        out = model.generate(packet)
        if out["status"] == "generated":
            packets.append({"case_index": i, "output": out})
    assert len(texts) == c["invalid_texts_accepted"] and len(packets) == c["invalid_packets_generated"]
    reading_failures = []
    for item in row["records"]:
        if item["stage"] == "read" and item["status"] == "read" and item["recovered"] != item["expected"]:
            read = model.read(item["input"])
            recovery = model.recover(read["packet"])
            assert recovery.get("meaning") == item["recovered"]
            reading_failures.append({"frozen_record": item, "recovery": recovery, "generation_from_packet": model.generate(read["packet"], "object")})
    assert len(reading_failures) == c["read_seen_wrong"] + c["read_heldout_wrong"]
    details.append({"seed": row["seed"], "dimension": row["dimension"], "fold": row["fold"], "fingerprint": model.fingerprint, "read_accepted_but_meaning_not_exact": reading_failures, "invalid_text_false_acceptances": texts, "invalid_packet_false_acceptances": packets})
record = {"source_freeze": verify_freeze(), "result_digest": fixed["result_digest"], "policy": "Diagnostic replay of frozen stress settings; no retraining data, threshold or acceptance-gate change.", "details": details}
with (ROOT / "results" / "STRESS_FAILURE_AUDIT.json").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(record, ensure_ascii=False, indent=2))
