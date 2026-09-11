import argparse
import json
from pathlib import Path
from ss_partial.runtime import PartialModel
from .memory import CorrectionMemory,METHODS

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('init');q.add_argument('--method',choices=METHODS,default='split_pair');q.add_argument('--seed',default='retention-code-0');q.add_argument('--out',required=True);q.add_argument('--model',required=True)
    for name in ('teach','complete','generate'):
        q=sub.add_parser(name);q.add_argument('--model',required=True);q.add_argument('--memory',required=True);q.add_argument('--episode',required=True);q.add_argument('--packet',required=True)
        if name=='teach':q.add_argument('--message',required=True);q.add_argument('--background',action='store_true');q.add_argument('--out',required=True)
        if name=='complete':q.add_argument('--out',required=True)
        if name=='generate':q.add_argument('--order',choices=('preserve','reverse'),default='preserve');q.add_argument('--goals',nargs='+')
    a=p.parse_args();model=PartialModel.load(a.model);load=lambda f:json.loads(Path(f).read_text(encoding='utf-8'))
    if a.command=='init':CorrectionMemory(model.codec.candidates,a.method,a.seed).save(a.out);print('{"status":"initialized"}');return
    memory=CorrectionMemory.load(a.memory,model.codec.candidates);packet=load(a.packet)
    if a.command=='teach':
        from .learning import teach
        r=teach(model,memory,a.episode,packet,load(a.message),not a.background);memory.save(a.out)
        r={'status':r['status'],'memory_update':r['memory_update'],'local_audit':r['local_update']['audit']}
    elif a.command=='complete':
        from .runtime import complete
        r=complete(model,memory,a.episode,packet)
        if 'packet' in r:
            with Path(a.out).open('x',encoding='utf-8') as f:json.dump(r['packet'],f,ensure_ascii=False,allow_nan=False)
            r={k:v for k,v in r.items() if k!='packet'}
    else:
        from .runtime import generate
        r=generate(model,memory,a.episode,packet,a.order,a.goals)
    print(json.dumps(r,ensure_ascii=False,allow_nan=False))
    if r['status'] in ('needs_information','abstain'):raise SystemExit(2)

if __name__=='__main__':main()
