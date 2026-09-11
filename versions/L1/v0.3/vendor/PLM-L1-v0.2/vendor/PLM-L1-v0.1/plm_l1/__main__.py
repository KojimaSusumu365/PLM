import argparse
import json
from pathlib import Path
from .runtime import Model


def write_new(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="PLM-L1 v0.1 controlled Japanese SS language experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("--out", required=True)
    train.add_argument("--seed", default="development-0")
    read = commands.add_parser("read")
    read.add_argument("--model", required=True)
    read.add_argument("--text", required=True)
    read.add_argument("--out", required=True, help="signal-only packet; original text/slots excluded")
    generate = commands.add_parser("generate")
    generate.add_argument("--model", required=True)
    generate.add_argument("--packet", required=True)
    generate.add_argument("--goal", default="object_first")
    args = parser.parse_args()
    if args.command == "train":
        from .training import fit
        model = fit(args.seed)
        model.save(args.out)
        result = {"status": "trained", "fingerprint": model.fingerprint, "statistics": model.meta["memory_statistics"]}
    elif args.command == "read":
        result = Model.load(args.model).read(args.text)
        if result["status"] == "read":
            write_new(args.out, result.pop("packet"))
    else:
        result = Model.load(args.model).generate(json.loads(Path(args.packet).read_text(encoding="utf-8")), args.goal)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] != "abstain" else 2


if __name__ == "__main__":
    raise SystemExit(main())
