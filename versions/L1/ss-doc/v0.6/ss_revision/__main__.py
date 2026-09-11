import argparse,json
from pathlib import Path
from ss_partial.runtime import PartialModel
from .memory import RevisionMemory,METHODS

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ('init','open','teach','generate'):
        q=sub.add_parser(name);q.add_argument('--model',required=True)
        if name=='init':
            q.add_argument('--method',choices=METHODS,default='versioned_pair');q.add_argument('--seed',default='revision-code-0')
        else:
            q.add_argument('--memory',required=True);q.add_argument('--scope',required=True);q.add_argument('--packet',required=True)
        if name in ('init','open','teach'):q.add_argument('--out',required=True)
        if name=='open':q.add_argument('--background',action='store_true')
        if name=='teach':q.add_argument('--message',required=True);q.add_argument('--packet-out',required=True)
        if name=='generate':q.add_argument('--order',choices=('preserve','reverse'),default='preserve')
    a=p.parse_args();model=PartialModel.load(a.model);read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
    if a.command=='init':
        RevisionMemory(model.codec.candidates,a.method,a.seed).save(a.out);print('{"status":"initialized"}');return
    memory=RevisionMemory.load(a.memory,model.codec.candidates);scope=read(a.scope);packet=read(a.packet)
    if a.command=='open':
        from .learning import begin
        root=begin(model,memory,scope,packet,not a.background);memory.save(a.out);r={'status':'opened','root':root}
    elif a.command=='teach':
        from .learning import teach
        if Path(a.out).exists() or Path(a.packet_out).exists():raise ValueError('output_already_exists')
        r=teach(model,memory,scope,packet,read(a.message));memory.save(a.out)
        with Path(a.packet_out).open('x',encoding='utf-8') as f:json.dump(r.pop('packet'),f,ensure_ascii=False,allow_nan=False)
    else:
        from .runtime import generate
        r=generate(model,memory,scope,packet,a.order)
    print(json.dumps(r,ensure_ascii=False,allow_nan=False))
    if r['status'] in ('needs_information','abstain'):raise SystemExit(2)

if __name__=='__main__':main()
