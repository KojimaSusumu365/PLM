import argparse
import json
from pathlib import Path
from .runtime import PairReader
from .compat import generator
from .bridge import generate, translate


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="SS pair-trained controlled-language reader")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--pairs", required=True)
    train.add_argument("--lexicon", required=True)
    train.add_argument("--seed", default="pair-development-0")
    train.add_argument("--out", required=True)
    read = commands.add_parser("read")
    read.add_argument("--model", required=True)
    read.add_argument("--text", required=True)
    read.add_argument("--out", required=True)
    for name in ("generate", "bridge"):
        command = commands.add_parser(name)
        command.add_argument("--model", required=True)
        command.add_argument("--packet", required=True)
        if name == "generate":
            command.add_argument("--goal", default="object_first")
        else:
            command.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "train":
        from .training import fit
        model = fit(read_json(args.pairs), read_json(args.lexicon), seed=args.seed)
        model.save(args.out)
        result = {"status": "trained", "reader_fingerprint": model.fingerprint, "statistics": model.meta["statistics"],
                  "reader_trace_supervision": False, "supervision_fields": ["text", "meaning"]}
    else:
        model = PairReader.load(args.model)
        if args.command == "read":
            result = model.read(args.text)
            if result["status"] == "read":
                write_new(args.out, result.pop("packet"))
        elif args.command == "bridge":
            result = translate(model, read_json(args.packet), generator())
            if result["status"] == "bridged":
                write_new(args.out, result.pop("packet"))
        else:
            result = generate(model, read_json(args.packet), generator(), args.goal)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "abstain" else 0


if __name__ == "__main__":
    raise SystemExit(main())
