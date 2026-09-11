import argparse,json
from pathlib import Path
from ss_multicode.model import Model
from .selection import select,STRATEGIES


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('query');q.add_argument('--model',required=True);q.add_argument('--input',required=True)
    q=sub.add_parser('select');q.add_argument('--model',required=True);q.add_argument('--state',required=True)
    q=sub.add_parser('start');q.add_argument('--learner',required=True);q.add_argument('--pool',required=True);q.add_argument('--config',required=True);q.add_argument('--strategy',choices=STRATEGIES,required=True);q.add_argument('--seed',default='acq-0');q.add_argument('--out',required=True)
    for name in ('ask','export'):
        q=sub.add_parser(name);q.add_argument('--session',required=True);q.add_argument('--out',required=True)
    q=sub.add_parser('background-ask');q.add_argument('--session',required=True);q.add_argument('--input',required=True);q.add_argument('--out',required=True)
    for name in ('teach','background-teach'):
        q=sub.add_parser(name);q.add_argument('--session',required=True);q.add_argument('--request',required=True);q.add_argument('--feedback',required=True);q.add_argument('--out',required=True)
    a=p.parse_args()
    def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
    def write(path,obj):
        with Path(path).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
    try:
        if a.command=='query':
            ps=Model.load(a.model).predict(read(a.input));print(json.dumps(ps));return 0 if all(p['accepted'] is not None for p in ps) else 2
        if a.command=='select':print(json.dumps(select(Model.load(a.model),read(a.state))));return 0
        from .session import Session
        if a.command=='start':
            from ss_multicode.learning import Learner
            s=Session(Learner.load(a.learner),read(a.pool),a.strategy,a.seed,read(a.config));s.save(a.out);print(json.dumps({'fingerprint':s.fingerprint}));return 0
        s=Session.load(a.session)
        if a.command in ('ask','export','background-ask'):
            obj=s.ask() if a.command=='ask' else s.selection_state if a.command=='export' else s.background_question(read(a.input))
            write(a.out,obj);print(json.dumps(obj));return 0
        request=read(a.request);fb=read(a.feedback)
        new=s.answer(request,fb) if a.command=='teach' else s.background_answer(request,fb)
        new.save(a.out);print(json.dumps({'fingerprint':new.fingerprint,'acquired':new.acquired,'background_teachers':new.background_count}));return 0
    except (ValueError,KeyError,TypeError,FileExistsError) as e:
        print(json.dumps({'status':'rejected','reason':str(e)}));return 2


if __name__=='__main__':raise SystemExit(main())
