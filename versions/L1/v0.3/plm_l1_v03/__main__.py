import argparse
import json
from pathlib import Path
from .runtime import Writer


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--pairs", required=True)
    train.add_argument("--lexicon", required=True)
    train.add_argument("--out", required=True)
    train.add_argument("--seed", default="writer-development-0")
    train.add_argument("--dimension", type=int, default=8192)
    for name in ("encode", "read", "generate"):
        command = sub.add_parser(name)
        command.add_argument("--model", required=True)
        if name == "generate":
            command.add_argument("--packet", required=True)
            command.add_argument("--goal", choices=("subject", "object"), default="object")
        else:
            command.add_argument("--out", required=True)
            command.add_argument("--meaning" if name == "encode" else "--text", required=True)
    args = parser.parse_args()
    try:
        if args.command == "train":
            from .training import fit
            model = fit(load(args.pairs), load(args.lexicon), seed=args.seed, dimension=args.dimension)
            model.save(args.out)
            result = {"status": "trained", "writer_fingerprint": model.fingerprint, "statistics": model.meta["statistics"]}
        else:
            model = Writer.load(args.model)
            if args.command == "generate":
                result = model.generate(load(args.packet), args.goal)
            elif args.command == "encode":
                write(args.out, model.encode(load(args.meaning)))
                result = {"status": "encoded"}
            else:
                from .bridge import fixed_reader, translate
                reader = fixed_reader()
                reading = reader.read(args.text)
                if reading["status"] == "read":
                    result = translate(reader, reading["packet"], model)
                    if result["status"] == "bridged":
                        write(args.out, result.pop("packet"))
                else:
                    result = {"status": "abstain", "reason": reading["reason"]}
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result["status"] == "abstain" else 0
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
