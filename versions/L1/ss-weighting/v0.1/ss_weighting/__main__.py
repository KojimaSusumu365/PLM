import argparse
import json
from .memory import Memory


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    t = sub.add_parser('train')
    t.add_argument('--input', required=True)
    t.add_argument('--out', required=True)
    t.add_argument('--dimension', type=int, default=128)
    t.add_argument('--seed', default='weight-user')
    t.add_argument('--method', choices=('uniform', 'positive', 'residual'), default='positive')
    q = sub.add_parser('query')
    q.add_argument('--model', required=True)
    q.add_argument('--input', required=True)
    a = p.parse_args()
    from pathlib import Path
    value = json.loads(Path(a.input).read_text(encoding='utf-8'))
    if a.command == 'train':
        from .training import fit
        model, audit = fit(value, dimension=a.dimension, seed=a.seed, method=a.method)
        model.save(a.out)
        print(json.dumps(audit, ensure_ascii=False))
    else:
        model = Memory.load(a.model)
        results = model.predict(value)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(r['value'] is not None for r in results) else 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
