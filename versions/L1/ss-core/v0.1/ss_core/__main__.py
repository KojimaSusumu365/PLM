import argparse
import json
from pathlib import Path
from plm_l1_v09.component.algebra import canonical
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from .runtime import generate_received

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def main():
    parser = argparse.ArgumentParser(description='Time-domain SS memory experiment 0.1')
    parser.add_argument('action', choices=('learn','generate'))
    for field in ('model','wire','message-id','scope'):
        parser.add_argument('--'+field, required=True)
    parser.add_argument('--memory')
    parser.add_argument('--out')
    parser.add_argument('--chunk', type=int, default=1)
    parser.add_argument('--order', choices=('preserve','reverse'), default='preserve')
    parser.add_argument('--goals', nargs=2, choices=('subject','object'))
    a = parser.parse_args()
    model = PartialModel.load(a.model)
    memory = RevisionMemory.load(a.memory, model.codec.candidates) if a.memory else RevisionMemory(model.codec.candidates)
    if a.action == 'learn':
        if not a.out:
            parser.error('--out required for learn')
        from .learning import learn_received
        updated, result = learn_received(model,memory,read(a.scope),read(a.wire),a.message_id,chunk=a.chunk)
        if result['status'] == 'learned':
            updated.save(a.out)
    else:
        if not a.memory:
            parser.error('--memory required for generate')
        result = generate_received(model,memory,read(a.scope),read(a.wire),a.message_id,
                                   order=a.order,goals=a.goals,chunk=a.chunk)
    print(canonical(result))
    return 0 if result['status'] in ('learned','generated') else 2

if __name__ == '__main__':
    raise SystemExit(main())
