import argparse
import json
from pathlib import Path
from ss_multicode.model import Model
from .selection import STRATEGIES, select


def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('query'); q.add_argument('--model', required=True); q.add_argument('--input', required=True)
    q = sub.add_parser('select'); q.add_argument('--model', required=True); q.add_argument('--pool', required=True); q.add_argument('--strategy', choices=STRATEGIES, required=True); q.add_argument('--seed', default='acq-0'); q.add_argument('--index', type=int, default=0)
    s = sub.add_parser('start'); s.add_argument('--learner', required=True); s.add_argument('--pool', required=True); s.add_argument('--strategy', choices=STRATEGIES, required=True); s.add_argument('--seed', default='acq-0'); s.add_argument('--out', required=True)
    q = sub.add_parser('ask'); q.add_argument('--session', required=True); q.add_argument('--out', required=True)
    t = sub.add_parser('teach'); t.add_argument('--session', required=True); t.add_argument('--request', required=True); t.add_argument('--feedback', required=True); t.add_argument('--out', required=True)
    a = p.parse_args()
    def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
    try:
        if a.command == 'query':
            ps = Model.load(a.model).predict(read(a.input)); print(json.dumps(ps, ensure_ascii=False))
            return 0 if all(p['accepted'] is not None for p in ps) else 2
        if a.command == 'select':
            print(json.dumps(select(Model.load(a.model), read(a.pool), a.strategy, a.seed, a.index), ensure_ascii=False)); return 0
        from .session import Session
        if a.command == 'start':
            from ss_multicode.learning import Learner
            s = Session(Learner.load(a.learner), read(a.pool), a.strategy, a.seed); s.save(a.out)
            print(json.dumps({'fingerprint': s.fingerprint})); return 0
        s = Session.load(a.session)
        if a.command == 'ask':
            req = s.ask()
            with Path(a.out).open('x', encoding='utf-8') as f: json.dump(req, f, ensure_ascii=False, indent=2)
            print(json.dumps(req, ensure_ascii=False)); return 0
        new = s.answer(read(a.request), read(a.feedback)); new.save(a.out)
        print(json.dumps({'fingerprint': new.fingerprint, 'teachers_acquired': len(new.acquired)})); return 0
    except (ValueError, KeyError, TypeError, FileExistsError) as e:
        print(json.dumps({'status': 'rejected', 'reason': str(e)})); return 2


if __name__ == '__main__': raise SystemExit(main())
