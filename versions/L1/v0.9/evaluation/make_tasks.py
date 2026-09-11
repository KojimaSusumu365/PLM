"""Synthetic supervised dependencies; dependency annotations NEVER enter select()."""
import argparse
import itertools
import json
from pathlib import Path
import random

FAMILIES=('unary','xor2','and2','switch3','parity3')

def tasks(split):
    result=[]
    for family in FAMILIES:
        for replicate in range(2):
            rng=random.Random(f'plm-v09/{split}/{family}/{replicate}')
            fields=['f'+str(i) for i in range(5)]; rng.shuffle(fields)
            labels=['label:'+str(i) for i in range(2)]; rng.shuffle(labels)
            rows=[]
            for cues in itertools.product((0,1),repeat=3):
                a,b,c=cues
                y={'unary':a,'xor2':a^b,'and2':a&b,'switch3':b if a else c,'parity3':a^b^c}[family]
                nuisance=list(itertools.product((0,1),repeat=2)); rng.shuffle(nuisance)
                for rank,noise in enumerate(nuisance):
                    rows.append({'context':dict(zip(fields,cues+noise)),'label':labels[y],'rank':rank})
            for n in (8,16,24):
                for noise_count in (0, max(1,n//10)):
                    training=[{'context':r['context'],'label':r['label']} for r in rows if r['rank']<n//8]
                    flipped=rng.sample(range(n),noise_count)
                    for i in flipped: training[i]['label']=labels[1-labels.index(training[i]['label'])]
                    testing=[{'context':r['context'],'label':r['label']} for r in rows if r['rank']==3]
                    result.append({'id':f'{split}/{family}/{replicate}/{n}/{noise_count}',
                                   'family':family,'replicate':replicate,'train_count':n,'flipped_labels':noise_count,
                                   'true_dependencies':sorted(fields[:1 if family=='unary' else 2 if family in ('xor2','and2') else 3]),
                                   'train':training,'test':testing,
                                   'unregistered':[{'context':{f:2 for f in fields}}]})
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); a=p.parse_args()
    target=Path(a.out); target.mkdir(parents=True,exist_ok=True)
    for split in ('development','evaluation'):
        with (target/('dependencies_'+split+'.json')).open('x',encoding='utf-8') as f:
            f.write(json.dumps(tasks(split),ensure_ascii=False,indent=2)+'\n')
