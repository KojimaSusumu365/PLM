import argparse
import json
from pathlib import Path
from .runtime import State


def main():
    p = argparse.ArgumentParser(description='Observation-only SS teacher-trace experiment')
    sub = p.add_subparsers(dest='command', required=True)
    q = sub.add_parser('observe'); q.add_argument('--state', required=True); q.add_argument('--input', required=True)
    q = sub.add_parser('ask'); q.add_argument('--state', required=True); q.add_argument('--input', required=True); q.add_argument('--out', required=True)
    q = sub.add_parser('teach'); q.add_argument('--state', required=True); q.add_argument('--request', required=True); q.add_argument('--feedback', required=True); q.add_argument('--out', required=True)
    a = p.parse_args(); state = State.load(a.state)
    read = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    if a.command == 'observe':
        print(json.dumps(state.observe(read(a.input)), ensure_ascii=False, indent=2)); return
    from .learning import question, answer
    if a.command == 'ask':
        with Path(a.out).open('x', encoding='utf-8') as f:
            json.dump(question(state, read(a.input)), f, ensure_ascii=False, indent=2)
    else:
        answer(state, read(a.request), read(a.feedback)).save(a.out)


if __name__ == '__main__':
    main()
