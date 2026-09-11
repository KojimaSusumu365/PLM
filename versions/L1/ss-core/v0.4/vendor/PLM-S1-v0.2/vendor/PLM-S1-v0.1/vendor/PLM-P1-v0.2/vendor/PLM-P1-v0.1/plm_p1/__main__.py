import argparse
import json
from pathlib import Path
from .adapter import from_r1_envelope, source_refs
from .core import PhaseCodebook, encode, decode, require
from .packet import to_packet, from_packet


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON number")
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=pairs, parse_constant=invalid)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="PLM-P1 v0.1 phase-code numerical observations")
    sub = parser.add_subparsers(dest="command", required=True)
    enc = sub.add_parser("encode")
    enc.add_argument("--input", required=True)
    enc.add_argument("--kind", choices=["frames", "r1-envelope"], default="frames")
    enc.add_argument("--out", required=True)
    enc.add_argument("--dimension", type=int, default=2048)
    enc.add_argument("--seed", default="plm-p1-v01")
    dec = sub.add_parser("decode")
    dec.add_argument("--packet", required=True)
    dec.add_argument("--query", required=True)
    dec.add_argument("--out", required=True)
    dec.add_argument("--expected-codebook", help="Optional separately pinned codebook spec JSON")
    chk = sub.add_parser("validate-packet")
    chk.add_argument("--packet", required=True)
    args = parser.parse_args()
    try:
        if args.command == "encode":
            frames = load_json(args.input)
            if args.kind == "r1-envelope":
                frames = from_r1_envelope(frames)
            book = PhaseCodebook(args.dimension, args.seed)
            packet = to_packet(encode(frames, book), None, book, source_refs=source_refs(frames))
            write_json(args.out, packet)
            result = {"packet_written": True, "frames": len(frames), "dimension": book.dimension, "inference_enabled": False}
        else:
            expected = None
            if args.command == "decode" and args.expected_codebook:
                spec = load_json(args.expected_codebook)
                expected = PhaseCodebook(spec["dimension"], spec["seed"])
                require(expected.spec == spec, "Unsupported expected codebook")
            values, mask, book = from_packet(load_json(args.packet), expected_codebook=expected)
            if args.command == "validate-packet":
                result = {"packet_valid": True, "dimension": book.dimension, "observed_components": int(mask.sum()), "inference_enabled": False}
            else:
                query = load_json(args.query)
                require(type(query) is dict and set(query) == {"document_id", "event_id", "role", "candidates"}, "Query must not contain gold/expected assignments")
                result = decode(values, book, **query, mask=mask)
                write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(2, "Rejected: " + str(error) + "\n")


if __name__ == "__main__":
    main()
