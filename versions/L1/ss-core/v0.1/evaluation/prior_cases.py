import copy,itertools,random
from plm_l1_v09.component.algebra import canonical,digest
from ss_partial.contract import from_meaning,to_meaning,cell
from .integrity import ROOT,read
from .oracle import render

def scene(m):return digest(canonical(sorted([{k:v for k,v in e.items() if k!='id'} for e in m['events']],key=canonical)))
def exclusions():
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];used=set(read(ROOT/'data/DELAY_EXCLUSIONS.json'))
    for ds in read(ROOT/'data/DELAY_DATASETS.json')['splits'].values():
        for c in ds['cases']:
            states=[c['initial']]+[s['known'] for s in c['steps']]
            if c['kind']=='focal':
                old=copy.deepcopy(c['final']);a=c['scope']['mutable'][0]
                old['cells'][a]=cell('known',[next(v for v in c['history_values'][a] if v!=old['cells'][a]['candidates'][0])]);states.append(old)
            used.update(scene(to_meaning(o,lex)) for o in states)
    for name in ('temporal_train.json','doc_v01_regression.json','doc_v02_scenes.json'):
        for row in read(ROOT/'data'/name):used.add(scene(row['meaning']))
    return used

def build():
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];seen=exclusions();initial=len(seen);splits={}
    for split,count in (('development',4),('evaluation',12)):
        rng=random.Random('l1-p1-s1-01/'+split);rows=[]
        for i in range(count):
            n=2+i%2
            while True:
                events=[]
                for j in range(n):
                    a,b=rng.sample(lex['subject'],2);events.append({'id':f'event:{j}','subject':a,'object':b,
                        **{r:rng.choice(lex[r]) for r in ('predicate','polarity','modality')}})
                relations=[]
                for a,b in itertools.combinations(range(n),2):
                    x,y=f'event:{a}',f'event:{b}';v=rng.randrange(3) if b==a+1 else 0
                    relations.append({'pair':[x,y],'kind':'unknown' if v==0 else 'before','source':None if v==0 else x if v==1 else y,'target':None if v==0 else y if v==1 else x})
                m={'events':events,'relations':relations,'presentation':[f'event:{j}' for j in range(n)]};key=scene(m)
                if key not in seen:seen.add(key);break
            last=f'event:{n-1}';pairs=[('event:0/subject',last+'/object'),('event:0/object',last+'/subject'),
                ('event:0/predicate',last+'/polarity'),('event:0/polarity',last+'/modality'),('time/event:0,event:1',last+'/subject'),('event:0/object',last+'/predicate')]
            targets=list(pairs[i%6]);known=from_meaning(m,lex);query=copy.deepcopy(known)
            for t in targets:query['cells'][t]=cell('unobserved',[])
            rows.append({'id':split+'/'+str(i),'scope':{'episode':'bridge01-'+split+'-'+str(i),'mutable':targets},
                         'meaning':m,'known':known,'query':query,'text':render(m,['subject']*n),'scene_fingerprint':key})
        splits[split]=rows
    return {'schema':'l1-p1-s1-corpus-01','splits':splits,'prior_excluded_scenes':initial,'unique_new_scenes':16,
            'known_vocabulary_and_grammar_only':True,'eligible_for_inference':False}
