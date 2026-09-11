import argparse,json
from pathlib import Path
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from .memory import SelectorMemory
from .runtime import Workset,choose,POLICIES

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('choose','confirm'));p.add_argument('--model',required=True)
    p.add_argument('--memory',required=True);p.add_argument('--workset',required=True);p.add_argument('--selector')
    p.add_argument('--policy',choices=POLICIES,default='ss_learned');p.add_argument('--history');p.add_argument('--step',type=int,default=0)
    p.add_argument('--answer');p.add_argument('--out');p.add_argument('--seed',default='selection-order-06');a=p.parse_args()
    read=lambda path:json.loads(Path(path).read_text(encoding='utf-8'))
    model=PartialModel.load(a.model);m=RevisionMemory.load(a.memory,model.codec.candidates);work=Workset(model,read(a.workset))
    excluded=read(a.history) if a.history else []
    if a.command=='choose':
        selector=SelectorMemory.load(a.selector) if a.selector else None
        r=choose(m,work,a.policy,selector,excluded,a.seed,a.step)
    else:
        from .feedback import answer
        if not a.answer or not a.out or Path(a.out).exists():raise ValueError('new_output_and_answer_required')
        value=read(a.answer)
        if set(value)!= {'question','value'}:raise ValueError('answer_contract')
        r=answer(model,m,work,value['question'],value['value'],excluded);m.save(a.out)
    print(json.dumps(r,ensure_ascii=False,allow_nan=False))

if __name__=='__main__':main()
