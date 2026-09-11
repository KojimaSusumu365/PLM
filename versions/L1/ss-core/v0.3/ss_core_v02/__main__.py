import argparse,json
from pathlib import Path
from plm_l1_v09.component.algebra import canonical
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from .runtime import generate_received
from .store import Store

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def main():
    p=argparse.ArgumentParser(description='Guarded waveform SS learning 0.2')
    p.add_argument('action',choices=('learn','generate'))
    for name in ('model','scope','wire','message-id'):p.add_argument('--'+name,required=True)
    p.add_argument('--memory');p.add_argument('--out');p.add_argument('--chunk',type=int,default=37)
    p.add_argument('--method',choices=('single','mean4','unchecked','guard'),default='guard')
    p.add_argument('--order',choices=('preserve','reverse'),default='preserve')
    p.add_argument('--goals',nargs=2,choices=('subject','object'))
    a=p.parse_args()
    model=PartialModel.load(a.model)
    memory=Store.load(a.memory,model.codec.candidates) if a.memory else Store(RevisionMemory(model.codec.candidates))
    if a.action=='learn':
        if not a.out:p.error('--out required')
        from .transaction import apply_received
        memory,r=apply_received(model,memory,read(a.scope),read(a.wire),a.message_id,method=a.method,chunk=a.chunk)
        memory.save(a.out)
    else:
        if not a.memory:p.error('--memory required')
        r=generate_received(model,memory,read(a.scope),read(a.wire),a.message_id,order=a.order,goals=a.goals,chunk=a.chunk)
    print(canonical(r))
    return 0 if r['status'] in ('learned','generated') else 2

if __name__=='__main__':raise SystemExit(main())
