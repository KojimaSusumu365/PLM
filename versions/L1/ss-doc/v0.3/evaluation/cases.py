import copy
import itertools
import random
from plm_l1_v09.component.algebra import canonical,digest
from ss_partial.contract import from_meaning,cell,normalize,to_meaning
from .integrity import ROOT,read
from .oracle import render

def scene_key(m):return canonical(sorted([{k:v for k,v in e.items() if k!='id'} for e in m['events']],key=canonical))

def dataset(seed,development=False):
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];rng=random.Random('ssdoc03/'+str(seed))
    forbidden={scene_key(r['meaning']) for name in ('temporal_train.json','doc_v01_regression.json','doc_v02_scenes.json') for r in read(ROOT/'data'/name)}
    result=[];focal=8 if development else 24;background=32 if development else 256
    for index in range(focal+background):
        n=2+index%2
        while True:
            events=[]
            for i in range(n):
                a,b=rng.sample(lex['subject'],2)
                events.append({'id':f'event:{i}','subject':a,'object':b,**{r:rng.choice(lex[r]) for r in ('predicate','polarity','modality')}})
            relations=[]
            for i,j in itertools.combinations(range(n),2):
                a,b=f'event:{i}',f'event:{j}';v=rng.randrange(3) if j==i+1 else 0
                relations.append({'pair':[a,b],'kind':'unknown' if v==0 else 'before','source':None if v==0 else a if v==1 else b,'target':None if v==0 else b if v==1 else a})
            meaning={'events':events,'presentation':[f'event:{i}' for i in range(n)],'relations':relations}
            k=scene_key(meaning)
            if k not in forbidden:forbidden.add(k);break
        known=from_meaning(meaning,lex)
        targets=[k for k in known['cells'] if k!='time/event:0,event:2']
        position=([0,1,2,3,4,5,6,7,10,14,15,16][(index//2)%12] if n==3 and index<focal else (index//2)%len(targets))
        target=targets[position]
        truth=known['cells'][target]['candidates'][0]
        choices=('unspecified','before','after') if target.startswith('time/') else lex[target.rsplit('/',1)[1]]
        excluded={truth}
        if target.endswith('/subject'):excluded.add(known['cells'][target.replace('/subject','/object')]['candidates'][0])
        if target.endswith('/object'):excluded.add(known['cells'][target.replace('/object','/subject')]['candidates'][0])
        alternative=next(v for v in choices if v not in excluded)
        observation=copy.deepcopy(known);observation['cells'][target]=cell('ambiguous',[truth,alternative]);observation=normalize(observation,lex)
        result.append({'id':f'd{seed}/{index}','episode':'episode-'+format(rng.getrandbits(128),'032x'),
                       'kind':'focal' if index<focal else 'background','target':target,'truth':truth,'alternative':alternative,
                       'known':known,'observation':observation,'meaning':meaning,
                       'text':render(meaning,['subject' if i%2==0 else 'object' for i in range(n)])})
    return result

def fresh_observation(case,mode):
    o=copy.deepcopy(case['observation'])
    if mode in ('unobserved','unreadable'):o['cells'][case['target']]=cell(mode,[])
    elif mode=='explicit_new':o['cells'][case['target']]=cell('known',[case['alternative']])
    elif mode=='conflict':o['cells'][case['target']]['state']='conflict'
    elif mode=='changed_anchor':
        k=next(k for k in o['cells'] if k!=case['target'] and k.endswith('/polarity'))
        old=o['cells'][k]['candidates'][0];o['cells'][k]=cell('known',['polarity:negative' if old=='polarity:positive' else 'polarity:positive'])
    return o
