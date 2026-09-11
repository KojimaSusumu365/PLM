"""CLI: text/meaning pair training and numerical-only document transfer."""
import argparse
import json
from pathlib import Path
from .runtime import TemporalModel


def data(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path,value):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest='command',required=True)
    train=commands.add_parser('train')
    train.add_argument('--component-pairs',required=True); train.add_argument('--temporal-pairs',required=True)
    train.add_argument('--lexicon',required=True); train.add_argument('--seed',default='temporal-evaluation-0')
    train.add_argument('--dimension',type=int,default=8192); train.add_argument('--mode',default='bound',choices=('bound','partitioned','undirected')); train.add_argument('--out',required=True)
    for name in ('read','encode','recover','generate'):
        p=commands.add_parser(name); p.add_argument('--model',required=True)
        if name=='read': p.add_argument('--text',required=True)
        elif name=='encode': p.add_argument('--meaning',required=True)
        else: p.add_argument('--packet',required=True)
        if name in ('read','encode'): p.add_argument('--out',required=True)
        if name=='generate':
            p.add_argument('--goals',nargs=2,default=['subject','subject'],choices=('subject','object'))
            p.add_argument('--order',default='preserve',choices=('preserve','reverse'))
    a=parser.parse_args()
    try:
        if a.command=='train':
            from .training import fit
            m=fit(data(a.component_pairs),data(a.temporal_pairs),data(a.lexicon),seed=a.seed,dimension=a.dimension,mode=a.mode)
            m.save(a.out); out={'status':'trained','fingerprint':m.fingerprint,'eligible_for_inference':False}
        else:
            m=TemporalModel.load(a.model)
            if a.command=='read':
                out=m.read(a.text)
                if out['status']=='read':
                    write(a.out,out['packet']); out={k:v for k,v in out.items() if k!='packet'}
            elif a.command=='encode':
                write(a.out,m.encode(data(a.meaning))); out={'status':'encoded','eligible_for_inference':False}
            elif a.command=='recover': out=m.recover(data(a.packet))
            else: out=m.generate(data(a.packet),a.goals,a.order)
    except (ValueError,TypeError,KeyError,OSError) as error:
        out={'status':'abstain','reason':str(error),'packet':None,'text':None,'eligible_for_inference':False}
    print(json.dumps(out,ensure_ascii=False))
    return 2 if out['status']=='abstain' else 0


if __name__=='__main__':
    raise SystemExit(main())
