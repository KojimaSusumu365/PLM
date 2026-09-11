import itertools,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FAMILIES=('unary','xor2','and2','switch3','parity3','roles','polarity_modality')

def make_task(split,family,rep=0,small=False):
    rng=random.Random(f'v011/{split}/{family}/{rep}');fields=['f'+str(i) for i in range(6)];rng.shuffle(fields)
    labels=['class:0','class:1'];rng.shuffle(labels);groups=[]
    def row(cues,noise):
        a,b,c=cues;values=cues+noise
        if family=='roles':
            names=('太郎','花子');fields_local=['first_name','second_name','order','style0','style1','style2']
            vs=(names[a],names[b],('subject_first','object_first')[c])+tuple(str(x) for x in noise)
            y=f'subject:{names[b if c else a]}|object:{names[a if c else b]}'
            return {'context':dict(zip(fields_local,vs)),'label':y}
        if family=='polarity_modality':
            fields_local=['negative_marker','hypothesis_marker','style0','style1','style2','style3']
            y=('negative' if a else 'positive')+'|'+('hypothetical' if b else 'asserted')
            return {'context':dict(zip(fields_local,map(str,values))),'label':y}
        y={'unary':a,'xor2':a^b,'and2':a&b,'switch3':b if a else c,'parity3':a^b^c}[family]
        return {'context':dict(zip(fields,map(str,values))),'label':labels[y]}
    for cues in itertools.product((0,1),repeat=3):
        noise=list(itertools.product((0,1),repeat=3));rng.shuffle(noise)
        groups.append([row(cues,n) for n in noise])
    return {'id':f'{split}/{family}/{rep}'+('/small' if small else ''),'family':family,
            'train':[r for g in groups for r in g[:1 if small else 3]],'selection':[r for g in groups for r in g[3:5]],
            'calibration':[g[5] for g in groups],'test':[r for g in groups for r in g[6:]],
            'completion_oracle':[r for g in groups for r in g],
            'scope':'Exhaustive truth table is evaluator-only; no dependency metadata enters fit. Structured roles/markers are not raw-language parsing.'}

def ambiguous(split,rep):
    rng=random.Random(f'v011/{split}/ambiguity/{rep}');fields=['f'+str(i) for i in range(6)];rng.shuffle(fields);groups={}
    for a,b in itertools.product((0,1),repeat=2):
        noise=list(itertools.product((0,1),repeat=4));rng.shuffle(noise)
        groups[a,b]=[{'context':dict(zip(fields,map(str,(a,b)+n))),'label':'class:'+str((a,b)[rep%2])} for n in noise]
    return {'id':f'{split}/ambiguity/{rep}','family':'ambiguity',
            'train':[r for (a,b),g in groups.items() if a==b for r in g[:4]],
            'selection':[r for (a,b),g in groups.items() if a==b for r in g[4:6]],
            'calibration':[r for (a,b),g in groups.items() if a==b for r in g[6:8]],
            'test':[r for (a,b),g in groups.items() if a!=b for r in g[8:12]],
            'added':[r for (a,b),g in groups.items() if a!=b for r in g[:4]],
            'completion_oracle':[r for g in groups.values() for r in g]}

def tasks(split):
    return [make_task(split,f,r) for f in FAMILIES for r in range(2 if f not in ('roles','polarity_modality') else 1)]+[make_task(split,f,0,True) for f in FAMILIES[:5]]+[ambiguous(split,i) for i in range(2)]

def allowed(task,context):
    return sorted({r['label'] for r in task['completion_oracle'] if all(r['context'][k]==v for k,v in context.items())})

def semantic_queries(task):
    result=[];seen=set()
    for r in task['test']:
        for f in sorted(r['context']):
            c={k:v for k,v in r['context'].items() if k!=f};key=json.dumps(c,sort_keys=True)
            if key in seen:continue
            seen.add(key);result.append({'context':c,'allowed':allowed(task,c),'erased_field':f})
    result.append({'context':{},'allowed':allowed(task,{}),'erased_field':'all'})
    return result

if __name__=='__main__':
    for split in ('development','evaluation'):
        with (ROOT/'data'/(split+'.json')).open('x',encoding='utf-8') as f:f.write(json.dumps(tasks(split),ensure_ascii=False,indent=2)+'\n')
