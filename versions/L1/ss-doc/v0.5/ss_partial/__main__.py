import argparse
import json
from pathlib import Path
from .runtime import PartialModel


def main():
    parser = argparse.ArgumentParser(description='SS partial short-document experiment')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('read', 'encode', 'inspect', 'recover', 'generate', 'update'):
        p = sub.add_parser(name)
        p.add_argument('--model', required=True)
        if name == 'read':
            p.add_argument('--texts', nargs='+', required=True)
        elif name == 'encode':
            p.add_argument('--observation', required=True)
        else:
            p.add_argument('--packet', required=True)
        if name in ('read', 'encode', 'update'):
            p.add_argument('--out', required=True)
        if name == 'generate':
            p.add_argument('--order', choices=('preserve', 'reverse'), default='preserve')
            p.add_argument('--goals', nargs='+')
        if name == 'update':
            p.add_argument('--message', required=True)
    a = parser.parse_args()
    model = PartialModel.load(a.model)
    load = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    if a.command == 'read':
        from .reader import read
        result = read(model, a.texts)
    elif a.command == 'encode':
        result = {'status': 'encoded', 'packet': model.encode(load(a.observation))}
    elif a.command == 'update':
        from .update import apply
        result = apply(model, load(a.packet), load(a.message))
    elif a.command == 'generate':
        result = model.generate(load(a.packet), a.order, a.goals)
    else:
        result = getattr(model, a.command)(load(a.packet))
    if 'packet' in result:
        with Path(a.out).open('x', encoding='utf-8') as f:
            json.dump(result['packet'], f, ensure_ascii=False, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'packet'}, ensure_ascii=False, allow_nan=False))
    if result['status'] in ('abstain', 'rejected', 'needs_information', 'conflict'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
