import argparse
import json
from pathlib import Path
from .runtime import DocumentModel


def main():
    p=argparse.ArgumentParser(description='SS bounded short-document experiment')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('read','encode','recover','generate'):
        q=sub.add_parser(name);q.add_argument('--model',required=True)
        if name=='read':q.add_argument('--text',required=True)
        elif name=='encode':q.add_argument('--meaning',required=True)
        else:q.add_argument('--packet',required=True)
        if name in ('read','encode'):q.add_argument('--out',required=True)
        if name=='generate':q.add_argument('--order',choices=['preserve','reverse'],default='preserve');q.add_argument('--goals',nargs='+')
    q=sub.add_parser('train');q.add_argument('--component-pairs',required=True);q.add_argument('--temporal-pairs',required=True);q.add_argument('--lexicon',required=True);q.add_argument('--out',required=True)
    a=p.parse_args();load=lambda f:json.loads(Path(f).read_text(encoding='utf-8'))
    if a.command=='train':
        from .training import train
        train(load(a.component_pairs),load(a.temporal_pairs),load(a.lexicon)).save(a.out);return
    model=DocumentModel.load(a.model)
    if a.command=='read':out=model.read(a.text)
    elif a.command=='encode':out={'status':'encoded','packet':model.encode(load(a.meaning)),'eligible_for_inference':False}
    elif a.command=='recover':out=model.recover(load(a.packet))
    else:out=model.generate(load(a.packet),a.order,a.goals)
    if a.command in ('read','encode') and out['status']!='abstain':
        with Path(a.out).open('x',encoding='utf-8') as f:json.dump(out['packet'],f,ensure_ascii=False)
        print(json.dumps({k:v for k,v in out.items() if k!='packet'},ensure_ascii=False))
    else:print(json.dumps(out,ensure_ascii=False))
    if out['status']=='abstain':raise SystemExit(2)


if __name__=='__main__':main()
