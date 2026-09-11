"""Generate an inspectable masked-signal example and frozen-R1 adapter examples."""
from pathlib import Path
from plm_p1 import PhaseCodebook, encode, decode, to_packet, from_packet
from plm_p1.core import channel
from plm_p1.fixtures import make_frames, entity_candidates
from plm_p1.adapter import source_refs, r1_module, from_r1_envelope
from plm_p1.__main__ import write_json

ROOT = Path(__file__).resolve().parent


def main():
    out = ROOT / "examples"
    out.mkdir(exist_ok=True)
    frames = make_frames(4)
    book = PhaseCodebook(2048, "demo-p1-v01")
    memory = encode(frames, book)
    masked, mask = channel(memory, seed=6100, keep_fraction=0.25, noise_std=0.15, jitter_std=0.1)
    packet = to_packet(masked, mask, book, source_refs=source_refs(frames))
    values, observed, receiver = from_packet(packet, expected_codebook=book)
    query = {"document_id": frames[0]["document_id"], "event_id": frames[0]["event_id"],
             "role": "subject", "candidates": entity_candidates()}
    result = decode(values, receiver, **query, mask=observed)
    write_json(out / "INPUT_FRAMES.json", frames)
    write_json(out / "S1_OBSERVATION_PACKET.json", packet)
    write_json(out / "QUERY.json", query)
    write_json(out / "CODEBOOK.json", book.spec)
    write_json(out / "RECOVERY_RESULT.json", result)
    cases = {"negative": "The bank did not grant aid.", "hypothetical": "If the bank grants aid.",
             "quarantined_quote": '"The bank granted aid."', "revision": "Originally marked dog: reclassified as cat.",
             "same_concept_two_instances": ["A dog and another dog entered.", "They were photographed."]}
    adapter_rows = []
    r1 = r1_module()
    for name, inputs in cases.items():
        envelope = r1.export_observations(r1.analyze(inputs))
        adapted = from_r1_envelope(envelope)
        sample = encode(adapted, book)
        checks = []
        for frame in adapted:
            for role in ("polarity", "modality", "semantic_status"):
                true_symbol = frame["slots"][role]
                alternatives = [true_symbol, {"kind": "state", "id": "not_the_encoded_value", "scope": "global"}]
                decoded = decode(sample, book, frame["document_id"], frame["event_id"], role, alternatives)
                checks.append({"event_id": frame["event_id"], "role": role, "correct": decoded["selected"] == true_symbol,
                               "eligible_for_inference": decoded["eligible_for_inference"]})
        adapter_rows.append({"case": name, "source_inputs": inputs, "frames": adapted, "state_recovery_checks": checks})
    write_json(out / "R1_ADAPTER_EXAMPLES.json", {"scope": "transport and numerical preservation only, not independent meaning validation", "cases": adapter_rows})
    lines = ["# PLM-P1 v0.1 デモ", "",
             "同じConcept（DOG）の別個体を含む人工4出来事・28結合を重畳。2048成分のうち512成分を観測し、人工雑音と位相揺らぎを付加しました。", "",
             "照会: event-000 の subject。復号器に渡すのは信号、マスク、コードブック、照会キー、候補辞書だけです。", "",
             "結果: " + result["status"] + " / " + str(result["selected"]), "",
             "推論許可: false。これは符号化された値の数値回復であり、観察内容が事実であることの判定ではありません。", "",
             "S1_OBSERVATION_PACKET.jsonには正解のslotsを含めず、未観測成分は0にしています。原入力は検証者向けの別ファイルINPUT_FRAMES.jsonです。", "",
             "R1連携例は否定、仮定、引用による隔離、訂正、同種別個体。元観察をmetadataに保存し、S1信号パケットには元の役割対応表を含めません。", ""]
    (out / "DEMO_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("demo:", result["status"], result["selected"], "observed:", result["observed_components"])


if __name__ == "__main__":
    main()
