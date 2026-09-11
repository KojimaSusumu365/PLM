import argparse,json
from pathlib import Path
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from .session import Session
from .runtime import assess,generate,POLICIES

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ('start','plan','confirm','generate'):
        q=sub.add_parser(name);q.add_argument('--model',required=True);q.add_argument('--memory',required=True)
        if name=='start':q.add_argument('--scope',required=True);q.add_argument('--packet',required=True)
        else:q.add_argument('--session',required=True);q.add_argument('--policy',choices=POLICIES,default='ss_selective')
        if name in ('start','confirm'):q.add_argument('--out',required=True)
        if name=='confirm':q.add_argument('--answer',required=True);q.add_argument('--memory-out',required=True)
        if name=='generate':q.add_argument('--order',choices=('preserve','reverse'),default='preserve')
    a=p.parse_args();model=PartialModel.load(a.model);m=RevisionMemory.load(a.memory,model.codec.candidates)
    read=lambda path:json.loads(Path(path).read_text(encoding='utf-8'))
    if a.command=='start':Session(model,m,read(a.scope),read(a.packet)).save(a.out);r={'status':'started'}
    else:
        s=Session.load(a.session,model,m)
        if a.command=='plan':r=assess(model,m,s,a.policy)
        elif a.command=='generate':r=generate(model,m,s,a.policy,a.order)
        else:
            from .learning import confirm
            if Path(a.out).exists() or Path(a.memory_out).exists():raise ValueError('output_already_exists')
            answer=read(a.answer)
            if type(answer) is not dict or set(answer)!= {'question','value'}:raise ValueError('answer_contract')
            new,r=confirm(model,m,s,answer['question'],answer['value'],a.policy);m.save(a.memory_out);new.save(a.out)
    print(json.dumps(r,ensure_ascii=False,allow_nan=False))
    if r['status'] in ('needs_confirmation','abstain'):raise SystemExit(2)

if __name__=='__main__':main()
