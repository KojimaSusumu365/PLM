import argparse
import json
from pathlib import Path
from .core import Model


def main():
    p = argparse.ArgumentParser()
    commands = p.add_subparsers(dest='command', required=True)
    for name in ('train', 'start'):
        parser = commands.add_parser(name)
        parser.add_argument('--train', required=True)
        parser.add_argument('--out', required=True)
        parser.add_argument('--backend', choices=('ss', 'exact'), default='ss')
        parser.add_argument('--dimension', type=int, default=2048)
        parser.add_argument('--seed', default='evaluation-0')
        parser.add_argument('--retention', choices=('all', 'minimal'), default='all')
        if name == 'start':
            parser.add_argument('--pool', required=True)
    q = commands.add_parser('query')
    q.add_argument('--model', required=True)
    q.add_argument('--input', required=True)
    s = commands.add_parser('select')
    s.add_argument('--model', required=True)
    s.add_argument('--pool', required=True)
    s.add_argument('--strategy', choices=('active', 'random'), default='active')
    s.add_argument('--seed', default='acquisition-0')
    s.add_argument('--out')
    t = commands.add_parser('teach')
    t.add_argument('--session', required=True)
    t.add_argument('--request', required=True)
    t.add_argument('--label', required=True)
    t.add_argument('--out', required=True)
    a = p.parse_args()
    def read(path):
        return json.loads(Path(path).read_text(encoding='utf-8'))
    try:
        if a.command in ('train', 'start'):
            settings = dict(backend=a.backend, dimension=a.dimension, seed=a.seed, retention=a.retention)
            if a.command == 'train':
                from .training import fit
                model = fit(read(a.train), **settings)[0]
                model.save(a.out)
            else:
                from .teaching import Session
                session = Session(read(a.train), read(a.pool), settings)
                session.save(a.out)
                model = session.model
            result = {'status': 'trained', 'fingerprint': model.fingerprint, 'candidate_count': len(model.members), 'eligible_for_inference': False}
        elif a.command == 'query':
            result = Model.load(a.model).predict(read(a.input))
        elif a.command == 'select':
            result = Model.load(a.model).select(read(a.pool), a.strategy, a.seed)
            if a.out:
                with Path(a.out).open('x', encoding='utf-8') as f:
                    f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        else:
            from .teaching import Session
            session = Session.load(a.session).answer(read(a.request), a.label)
            session.save(a.out)
            result = {'status': 'trained', 'fingerprint': session.model.fingerprint, 'labels_received': len(session.receipts), 'eligible_for_inference': False}
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({'status': 'rejected', 'reason': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result.get('status') in ('abstain', 'no_request') else 0


if __name__ == '__main__':
    raise SystemExit(main())
