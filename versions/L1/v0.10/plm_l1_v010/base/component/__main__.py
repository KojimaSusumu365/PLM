import argparse
import json
from pathlib import Path
from .runtime import Model


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    fit = commands.add_parser("train")
    fit.add_argument("--pairs", required=True)
    fit.add_argument("--lexicon", required=True)
    fit.add_argument("--out", required=True)
    fit.add_argument("--seed", default="banked-development-0")
    fit.add_argument("--memory-mode", choices=("single", "split", "proof", "split_proof", "split_unchecked"), default="split_proof")
    fit.add_argument("--dimension", type=int, default=8192)
    for name in ("read", "encode", "generate"):
        p = commands.add_parser(name)
        p.add_argument("--model", required=True)
        if name == "generate":
            p.add_argument("--packet", required=True)
            p.add_argument("--goal", choices=("subject", "object"), default="object")
        else:
            p.add_argument("--text" if name == "read" else "--meaning", required=True)
            p.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "train":
            from .training import fit
            model = fit(load(args.pairs), load(args.lexicon), seed=args.seed, dimension=args.dimension, memory_mode=args.memory_mode)
            model.save(args.out)
            result = {"status": "trained", "fingerprint": model.fingerprint, "pair_count": model.meta["pair_count"], "statistics": model.meta["statistics"]}
        else:
            model = Model.load(args.model)
            if args.command == "read":
                result = model.read(args.text)
                if result["status"] == "read":
                    write(args.out, result.pop("packet"))
            elif args.command == "encode":
                write(args.out, model.encode(load(args.meaning)))
                result = {"status": "encoded"}
            else:
                result = model.generate(load(args.packet), args.goal)
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result["status"] == "abstain" else 0
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
