import argparse,json
from pathlib import Path
from plm_l1_v09.component.algebra import canonical
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from .runtime import receive,generate_received

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('receive','generate','learn'))
    parser.add_argument('--model',required=True);parser.add_argument('--wire',required=True);parser.add_argument('--message-id',required=True)
    parser.add_argument('--mode',choices=('spread','repeat'),default='spread');parser.add_argument('--memory');parser.add_argument('--scope');parser.add_argument('--out')
    parser.add_argument('--order',choices=('preserve','reverse'),default='preserve');a=parser.parse_args()
    model=PartialModel.load(a.model);wire=read(a.wire)
    if a.action=='receive':result=receive(model,wire,a.message_id,a.mode)
    else:
        if not a.scope:parser.error('--scope required')
        memory=RevisionMemory.load(a.memory,model.codec.candidates) if a.memory else RevisionMemory(model.codec.candidates)
        if a.action=='generate':result=generate_received(model,memory,read(a.scope),wire,a.message_id,a.mode,a.order)
        else:
            if not a.out:parser.error('--out required for learn')
            from .learning import learn_received
            memory,result=learn_received(model,memory,read(a.scope),wire,a.message_id,a.mode)
            if result['status']=='learned':memory.save(a.out)
    print(canonical(result));return 0 if result['status'] in ('received','generated','learned') else 2
if __name__=='__main__':raise SystemExit(main())
