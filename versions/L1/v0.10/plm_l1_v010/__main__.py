import argparse,json
from pathlib import Path
from .runtime import CommitteeModel

def data(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as f: f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    train=sub.add_parser('train')
    for name in ('component-pairs','selection-pairs','temporal-pairs','lexicon','out'): train.add_argument('--'+name,required=True)
    train.add_argument('--method',choices=('ss_multi','symbolic_multi','ss_single','v09_single'),default='ss_multi')
    train.add_argument('--selection-seed',default='candidate-evaluation-0'); train.add_argument('--selection-dimension',type=int,default=2048)
    for name in ('read','encode','recover','generate'):
        c=sub.add_parser(name); c.add_argument('--model',required=True)
        if name=='read': c.add_argument('--text',required=True)
        elif name=='encode': c.add_argument('--meaning',required=True)
        else: c.add_argument('--packet',required=True)
        if name in ('read','encode'): c.add_argument('--out',required=True)
        if name=='generate':
            c.add_argument('--goals',nargs=2,choices=('subject','object'),default=['subject','subject'])
            c.add_argument('--order',choices=('preserve','reverse'),default='preserve')
    a=p.parse_args()
    try:
        if a.command=='train':
            from .training import fit
            m=fit(data(a.component_pairs),data(a.selection_pairs),data(a.temporal_pairs),data(a.lexicon),method=a.method,selection_seed=a.selection_seed,selection_dimension=a.selection_dimension)
            m.save(a.out); result={'status':'trained','fingerprint':m.fingerprint,'members':len(m.members),'supported':m.meta['training']['supported'],'eligible_for_inference':False}
        else:
            m=CommitteeModel.load(a.model)
            if a.command=='read':
                result=m.read(a.text)
                if result['status']=='read': write(a.out,result.pop('packet'))
            elif a.command=='encode': write(a.out,m.encode(data(a.meaning))); result={'status':'encoded','eligible_for_inference':False}
            elif a.command=='recover': result=m.recover(data(a.packet))
            else: result=m.generate(data(a.packet),a.goals,a.order)
    except (ValueError,TypeError,KeyError,OSError) as e: result={'status':'abstain','reason':str(e),'packet':None,'text':None,'eligible_for_inference':False}
    print(json.dumps(result,ensure_ascii=False)); return 2 if result['status']=='abstain' else 0

if __name__=='__main__': raise SystemExit(main())
