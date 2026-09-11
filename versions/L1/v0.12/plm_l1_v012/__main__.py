import argparse
import json
from pathlib import Path
from .core import GuardedModel, POLICIES


def main():
    p = argparse.ArgumentParser()
    commands = p.add_subparsers(dest='command', required=True)
    q = commands.add_parser('query')
    q.add_argument('--model', required=True)
    q.add_argument('--input', required=True)
    q.add_argument('--policy', choices=POLICIES, default='completion')
    t = commands.add_parser('train')
    for key in ('train', 'selection', 'calibration', 'out'):
        t.add_argument('--' + key, required=True)
    t.add_argument('--representation', choices=('hybrid3', 'product', 'additive'), default='hybrid3')
    t.add_argument('--selector', choices=('validation', 'off'), default='validation')
    t.add_argument('--backend', choices=('ss', 'exact'), default='ss')
    t.add_argument('--dimension', type=int, default=2048)
    t.add_argument('--seed', default='development-0')
    a = p.parse_args()
    def read(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))
    try:
        if a.command == 'train':
            from .training import train_model
            model, _, _ = train_model(read(a.train), read(a.selection), read(a.calibration),
                                     representation=a.representation, selector=a.selector,
                                     backend=a.backend, dimension=a.dimension, seed=a.seed)
            model.save(a.out)
            result = {'status': 'trained', 'fingerprint': model.fingerprint, 'eligible_for_inference': False}
        else:
            result = GuardedModel.load(a.model).predict(read(a.input), policy=a.policy)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'rejected', 'reason': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] == 'abstain' else 0


if __name__ == '__main__':
    raise SystemExit(main())
