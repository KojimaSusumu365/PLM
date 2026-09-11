import argparse
import json
from pathlib import Path
from .runtime import EventModel


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path,value):
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def main():
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest="command",required=True)
    train=commands.add_parser("train")
    for name in ("pairs","lexicon","out"):
        train.add_argument("--"+name,required=True)
    train.add_argument("--component-seed",default="banked-evaluation-0")
    train.add_argument("--event-seed",default="events-development-0")
    train.add_argument("--dimension",type=int,default=8192)
    train.add_argument("--mode",choices=("bound","partitioned","unbound"),default="bound")
    for name in ("read","encode","recover","generate"):
        p=commands.add_parser(name)
        p.add_argument("--model",required=True)
        if name in ("read","encode"):
            p.add_argument("--text" if name=="read" else "--meaning",required=True)
            p.add_argument("--out",required=True)
        else:
            p.add_argument("--packet",required=True)
        if name=="generate":
            p.add_argument("--goals",nargs=2,choices=("subject","object"),default=["subject","subject"])
    args=parser.parse_args()
    try:
        if args.command=="train":
            from .training import fit
            model=fit(load(args.pairs),load(args.lexicon),component_seed=args.component_seed,event_seed=args.event_seed,dimension=args.dimension,mode=args.mode)
            model.save(args.out)
            result={"status":"trained","fingerprint":model.fingerprint,"component_fingerprint":model.component.fingerprint,"two_event_binding_learned":False}
        else:
            model=EventModel.load(args.model)
            if args.command=="read":
                result=model.read(args.text)
                if result["status"]=="read":
                    write(args.out,result.pop("packet"))
            elif args.command=="encode":
                write(args.out,model.encode(load(args.meaning)))
                result={"status":"encoded"}
            elif args.command=="recover":
                result=model.recover(load(args.packet))
            else:
                result=model.generate(load(args.packet),args.goals)
        print(json.dumps(result,ensure_ascii=False))
        return 2 if result["status"]=="abstain" else 0
    except (ValueError,TypeError,OSError,KeyError) as error:
        print(json.dumps({"status":"error","reason":str(error)},ensure_ascii=False))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
