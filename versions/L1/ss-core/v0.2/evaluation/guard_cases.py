import copy,random
from ss_partial.contract import from_meaning,to_meaning,cell
from .cases import PAIRS
from .prior_cases import scene,exclusions
from .oracle import render
from .integrity import ROOT,read

def build():
    lex=read(ROOT/'data/lexicon.json')['slot_candidates']
    seen=exclusions()
    for name in ('BRIDGE_CORPUS.json','CORPUS.json'):
        seen.update(c['scene_fingerprint'] for rows in read(ROOT/'data'/name)['splits'].values() for c in rows)
    excluded=len(seen);splits={}
    for split in ('development','evaluation'):
        rng=random.Random('guard-core02/'+split);rows=[]
        for kind,count in (('focal',4),('anchor',2),('background',2)):
            for i in range(count):
                targets=list(PAIRS[[0,2,3,4][i%4]])
                while True:
                    events=[]
                    for j in range(2):
                        a,b=rng.sample(lex['subject'],2)
                        events.append({'id':f'event:{j}','subject':a,'object':b,
                                       **{r:rng.choice(lex[r]) for r in ('predicate','polarity','modality')}})
                    v=rng.randrange(3)
                    m={'events':events,'presentation':['event:0','event:1'],'relations':[{
                        'pair':['event:0','event:1'],'kind':'unknown' if v==0 else 'before',
                        'source':None if v==0 else 'event:0' if v==1 else 'event:1',
                        'target':None if v==0 else 'event:1' if v==1 else 'event:0'}]}
                    known=from_meaning(m,lex);initial=copy.deepcopy(known)
                    if kind=='focal':
                        for t in targets:
                            inventory=['unspecified','before','after'] if t.startswith('time/') else lex[t.split('/')[1]]
                            old=known['cells'][t]['candidates'][0]
                            initial['cells'][t]=cell('known',[next(x for x in inventory if x!=old)])
                    signatures={scene(m),scene(to_meaning(initial,lex))}
                    if not signatures&seen:seen.update(signatures);break
                query=copy.deepcopy(known)
                for t in targets:query['cells'][t]=cell('unobserved',[])
                ident=split+'/'+kind+'/'+str(i)
                rows.append({'id':ident,'kind':kind,'scope':{'episode':'guard02/'+ident,'mutable':targets},
                    'known':known,'initial':initial,'meaning':m,'query':query,'text':render(m,['subject','subject']),
                    'initial_text':render(to_meaning(initial,lex),['subject','subject']),'scene_fingerprints':sorted(signatures)})
        splits[split]=rows
    return {'schema':'ss-core-guard-corpus-02','splits':splits,'prior_excluded_scenes':excluded,
            'new_documents':16,'new_scene_variants':len(seen)-excluded,'eligible_for_inference':False}
