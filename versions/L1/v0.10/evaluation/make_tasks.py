"""Frozen task generator. No dependency annotations are passed to learners."""
import argparse,itertools,json,random
from pathlib import Path

FAMILIES=('unary','xor2','and2','switch3','parity3')

def tasks(split):
    result=[]
    for family in FAMILIES:
        for rep in range(2):
            rng=random.Random(f'v010/{split}/{family}/{rep}')
            fields=['f'+str(i) for i in range(6)]; rng.shuffle(fields)
            labels=['label:0','label:1']; rng.shuffle(labels)
            groups=[]
            for cues in itertools.product((0,1),repeat=3):
                a,b,c=cues; y={'unary':a,'xor2':a^b,'and2':a&b,'switch3':b if a else c,'parity3':a^b^c}[family]
                nuisance=list(itertools.product((0,1),repeat=3)); rng.shuffle(nuisance)
                groups.append([{'context':dict(zip(fields,cues+noise)),'label':labels[y]} for noise in nuisance])
            for n in (8,16,24):
                for flips in (0,max(1,n//8)):
                    train=[dict(context=dict(r['context']),label=r['label']) for group in groups for r in group[:n//8]]
                    for i in rng.sample(range(len(train)),flips): train[i]['label']=labels[1-labels.index(train[i]['label'])]
                    result.append({'id':f'{split}/{family}/{rep}/{n}/{flips}','family':family,'replicate':rep,'train_count':n,'flipped_labels':flips,
                                   'true_dependencies':sorted(fields[:1 if family=='unary' else 2 if family in ('xor2','and2') else 3]),
                                   'train':train,'selection_validation':[r for g in groups for r in g[3:5]],
                                   'risk_calibration':[g[5] for g in groups],'evaluation':[r for g in groups for r in g[6:8]],
                                   'ood':[{'context':dict.fromkeys(fields,2)}]})
    return result

def ambiguity(split):
    result=[]
    for rep in range(4):
        rng=random.Random(f'v010/{split}/ambiguity/{rep}'); fields=['f'+str(i) for i in range(6)]; rng.shuffle(fields)
        labels=['label:0','label:1']; rng.shuffle(labels); correct=rep%2
        groups={}
        for a,b in itertools.product((0,1),repeat=2):
            noise=list(itertools.product((0,1),repeat=4)); rng.shuffle(noise)
            groups[a,b]=[{'context':dict(zip(fields,(a,b)+v)),'label':labels[(a,b)[correct]]} for v in noise]
        result.append({'id':f'{split}/ambiguous/{rep}','true_dependencies':[fields[correct]],'plausible_correlated_fields':fields[:2],
                       'train':[r for (a,b),g in groups.items() if a==b for r in g[:4]],
                       'selection_validation':[r for (a,b),g in groups.items() if a==b for r in g[4:6]],
                       'risk_calibration':[r for (a,b),g in groups.items() if a==b for r in g[6:8]],
                       'evaluation':[r for (a,b),g in groups.items() if a!=b for r in g[8:12]],
                       'added_examples':[r for (a,b),g in groups.items() if a!=b for r in g[:4]],
                       'scope':'Selected examples break correlation; clean supervised refit, not autonomous active learning.'})
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); a=p.parse_args(); out=Path(a.out)
    for split in ('development','evaluation'):
        for name,rows in (('dependencies',tasks(split)),('ambiguity',ambiguity(split))):
            with (out/(name+'_'+split+'.json')).open('x',encoding='utf-8') as f: f.write(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
