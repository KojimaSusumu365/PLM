"""v0.1 wire-compatible entity/state recovery; separate v2 pilot experiment wire."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import argparse
import json
from plm_p1.core import PhaseCodebook, encode, require
from plm_p1.adapter import from_r1_envelope, source_refs
from plm_p1.packet import to_packet, from_packet
from plm_p1.__main__ import load_json, write_json
from .recovery import Receiver
from .sync import FORMAT, synchronize, from_pilot_packet


def main():
    parser = argparse.ArgumentParser(description="PLM-P1 v0.2 observe-only numerical recovery")
    sub = parser.add_subparsers(dest="command", required=True)
    enc = sub.add_parser("encode")
    enc.add_argument("--input", required=True)
    enc.add_argument("--kind", choices=["frames", "r1-envelope"], default="frames")
    enc.add_argument("--out", required=True)
    enc.add_argument("--dimension", type=int, default=2048)
    enc.add_argument("--seed", default="plm-p1-v02-demo")
    dec = sub.add_parser("decode")
    dec.add_argument("--packet", required=True)
    dec.add_argument("--catalogue", required=True)
    dec.add_argument("--query", required=True)
    dec.add_argument("--expected-codebook", required=True)
    dec.add_argument("--out", required=True)
    chk = sub.add_parser("validate-packet")
    chk.add_argument("--packet", required=True)
    args = parser.parse_args()
    try:
        if args.command == "encode":
            frames = load_json(args.input)
            if args.kind == "r1-envelope":
                frames = from_r1_envelope(frames)
            book = PhaseCodebook(args.dimension, args.seed)
            write_json(args.out, to_packet(encode(frames, book), None, book, source_refs=source_refs(frames)))
            result = {"packet_written": True, "wire_codec": "unchanged_P1_v01", "inference_enabled": False}
        else:
            packet = load_json(args.packet)
            if args.command == "validate-packet":
                if packet.get("format") == FORMAT:
                    from_pilot_packet(packet)
                else:
                    from_packet(packet)
                result = {"packet_valid": True, "inference_enabled": False}
            else:
                spec = load_json(args.expected_codebook)
                book = PhaseCodebook(spec["dimension"], spec["seed"])
                require(book.spec == spec, "Invalid pinned codebook")
                query = load_json(args.query)
                require(type(query) is dict and set(query) == {"document_id", "event_id", "role", "candidates"}, "Query must not contain gold/assignments/offsets")
                sync_result = None
                if packet.get("format") == FORMAT:
                    values, mask, book, sync_result = synchronize(packet, expected_book=book)
                else:
                    values, mask, book = from_packet(packet, expected_codebook=book)
                receiver = Receiver(values, mask, book, load_json(args.catalogue))
                if sync_result is not None and sync_result["status"] != "aligned":
                    result = {"status": "abstain", "selected": None, "reason": "pilot_synchronization_failed", "eligible_for_inference": False}
                else:
                    result = receiver.scores(**query)
                if sync_result is not None:
                    result["synchronization"] = sync_result
                write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, "Rejected: " + str(error) + "\n")


if __name__ == "__main__":
    main()
