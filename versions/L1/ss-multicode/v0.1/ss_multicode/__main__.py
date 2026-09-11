import argparse
import json
from pathlib import Path
from .model import Model, SPECS


def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('start'); s.add_argument('--architecture', choices=list(SPECS), default='multi4'); s.add_argument('--seed', default='code-0'); s.add_argument('--out', required=True)
    q = sub.add_parser('query'); q.add_argument('--model', required=True); q.add_argument('--input', required=True)
    q = sub.add_parser('question'); q.add_argument('--learner', required=True); q.add_argument('--input', required=True); q.add_argument('--out', required=True)
    t = sub.add_parser('teach'); t.add_argument('--learner', required=True); t.add_argument('--request', required=True); t.add_argument('--feedback', required=True); t.add_argument('--out', required=True)
    a = p.parse_args()
    def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
    try:
        if a.command == 'query':
            results = Model.load(a.model).predict(read(a.input)); print(json.dumps(results, ensure_ascii=False))
            return 0 if all(r['accepted'] is not None for r in results) else 2
        from .learning import Learner
        if a.command == 'start':
            learner = Learner(Model(a.architecture, a.seed)); learner.save(a.out)
            print(json.dumps({'fingerprint': learner.fingerprint})); return 0
        learner = Learner.load(a.learner)
        if a.command == 'question':
            q = learner.question(read(a.input))
            with Path(a.out).open('x', encoding='utf-8') as f: json.dump(q['request'], f, ensure_ascii=False, indent=2)
            print(json.dumps(q['prediction'], ensure_ascii=False)); return 0
        new = learner.answer(read(a.request), read(a.feedback)); new.save(a.out)
        print(json.dumps({'step': new.step, 'fingerprint': new.fingerprint})); return 0
    except (ValueError, KeyError, TypeError, FileExistsError) as e:
        print(json.dumps({'status': 'rejected', 'reason': str(e)})); return 2


if __name__ == '__main__': raise SystemExit(main())
