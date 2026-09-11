import argparse,json
from pathlib import Path
from .core import Model,observe

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,x):
    with Path(p).open('x',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('train');t.add_argument('--train',required=True);t.add_argument('--selection',required=True);t.add_argument('--calibration',required=True);t.add_argument('--out',required=True)
    t.add_argument('--representation',choices=('additive','product','hybrid3'),default='hybrid3');t.add_argument('--selector',choices=('off','validation'),default='off');t.add_argument('--backend',choices=('ss','exact'),default='ss');t.add_argument('--dimension',type=int,default=2048);t.add_argument('--seed',default='evaluation-0')
    for name in ('query','encode','decode'):
        q=sub.add_parser(name);q.add_argument('--model',required=True);q.add_argument('--input',required=True)
        if name=='encode':q.add_argument('--out',required=True)
    o=sub.add_parser('observe');o.add_argument('--input',required=True);o.add_argument('--out',required=True);o.add_argument('--fraction',type=float,required=True);o.add_argument('--seed',default='mask-0')
    a=p.parse_args()
    if a.command=='train':
        from .training import fit,calibrate
        model,_,_=fit(load(a.train),load(a.selection),representation=a.representation,selector=a.selector,backend=a.backend,dimension=a.dimension,seed=a.seed)
        calibrate(model,load(a.calibration));model.save(a.out);print(json.dumps({'fingerprint':model.fingerprint,'eligible_for_inference':False}));return 0
    if a.command=='observe':write(a.out,observe(load(a.input),a.fraction,a.seed));return 0
    model=Model.load(a.model);value=load(a.input)
    if a.command=='encode':write(a.out,model.encode(value));return 0
    try:result=model.decode(value) if a.command=='decode' else model.predict(value)
    except ValueError as e:result={'value':None,'status':'abstain','reason':str(e),'eligible_for_inference':False}
    print(json.dumps(result,ensure_ascii=False));return 0 if result['status']=='accepted' else 2

if __name__=='__main__':raise SystemExit(main())
