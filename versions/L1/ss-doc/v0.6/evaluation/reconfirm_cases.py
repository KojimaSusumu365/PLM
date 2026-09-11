import copy,random
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import cell,normalize,to_meaning
from .cases import dataset as pool,scene_key
from .integrity import ROOT,read

KINDS=('current_known','stale_known','stale_partial','missing','conflict','ambiguous')

def make_case(source,index,split,focal,lex):
    o=copy.deepcopy(source['known']);n=o['count'];last=f'event:{n-1}'
    pairs=[('event:1/subject','event:1/object'),('event:0/subject',last+'/subject'),
           ('event:0/predicate',last+'/polarity'),('event:0/polarity',last+'/modality'),
           ('time/event:0,event:1',last+'/subject'),('event:0/object',last+'/predicate')]
    rotation=0 if split=='development' else int(split)%6
    a,b=pairs[(index+index//6+rotation)%6];targets=[a,b];initial=copy.deepcopy(o);steps=[]
    choices={t:(('unspecified','before','after') if t.startswith('time/') else lex[t.rsplit('/',1)[1]]) for t in targets}
    history={t:[o['cells'][t]['candidates'][0]] for t in targets}
    for j,t in enumerate((a,b,a,b,a) if focal else (a,a)):
        previous=o['cells'][t]['candidates'][0]
        value=previous if not focal and j==1 else choices[t][(choices[t].index(previous)+1)%len(choices[t])]
        history[t].append(value);o['cells'][t]=cell('known',[value]);o=normalize(o,lex)
        steps.append({'target':t,'value':value,'operation':'supply' if j==0 or not focal else 'revise','known':copy.deepcopy(o)})
    observation=copy.deepcopy(initial);observation['cells'][a]=cell('ambiguous',[initial['cells'][a]['candidates'][0],steps[0]['value']]);observation=normalize(observation,lex)
    return {'id':f'q{split}/{index}','scope':{'episode':'reconfirm-'+source['episode'],'mutable':targets},'kind':'focal' if focal else 'background',
            'query_kind':KINDS[index%6],'initial':initial,'observation':observation,'steps':steps,'final':steps[-1]['known'],'history_values':history}

def observation(case,mode=None):
    kind=mode or case['query_kind'];o=copy.deepcopy(case['final']);a,b=case['scope']['mutable']
    if kind=='current_known':return o
    old=next(v for v in case['history_values'][a] if v!=o['cells'][a]['candidates'][0])
    if kind in ('stale_known','stale_partial'):o['cells'][a]=cell('known',[old])
    if kind in ('stale_partial','missing'):o['cells'][b]=cell('unobserved',[])
    if kind=='missing':o['cells'][a]=cell('unobserved',[])
    if kind=='conflict':o['cells'][a]=cell('conflict',[old,case['final']['cells'][a]['candidates'][0]])
    if kind=='ambiguous':
        for t in (a,b):
            v=o['cells'][t]['candidates'][0];alt=next(x for x in case['history_values'][t] if x!=v)
            o['cells'][t]=cell('ambiguous',[v,alt])
    return o

def footprint(case,lex):
    states=[case['initial']]+[s['known'] for s in case['steps']]
    if case['kind']=='focal':states.append(observation(case,'stale_known'))
    return {digest(scene_key(to_meaning(o,lex))) for o in states}

def build(exclusions):
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];used=set(exclusions);splits={};audit=[]
    for split,focal,background in (('development',6,24),('300',12,256),('301',12,256)):
        accepted=[];batch=0;rejected=0
        while len(accepted)<focal+background:
            for source in pool('ssdoc05/'+split+'/'+str(batch)):
                i=len(accepted)
                if i==focal+background:break
                n=2+(i//6)%2 if i<focal else 2+i%2
                if source['known']['count']!=n:continue
                c=make_case(source,i,split,i<focal,lex);keys=footprint(c,lex)
                if keys&used:rejected+=1;continue
                used.update(keys);accepted.append(c)
            batch+=1;assert batch<20
        order=list(range(focal));random.Random('ssdoc05/query-order/'+split).shuffle(order)
        splits[split]={'cases':accepted,'query_order':order}
        audit.append({'split':split,'focal':focal,'background':background,'collision_rejections':rejected,'batches':batch})
    return {'schema':'ssdoc05-frozen-datasets','splits':splits,'construction_audit':audit,'coarse_scene_signature':'sorted events without IDs, presentation or temporal edges'}

def audit_datasets(data,exclusions):
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];seen=set(exclusions);ids=set();rows=[]
    for name,split in data['splits'].items():
        count=0
        for c in split['cases']:
            keys=footprint(c,lex);assert not keys&seen,'scene_overlap';seen.update(keys);count+=len(keys)
            assert c['scope']['episode'] not in ids;ids.add(c['scope']['episode'])
        rows.append({'split':name,'episodes':len(split['cases']),'distinct_scene_fingerprints':count})
    return {'passed':True,'rows':rows,'episodes':len(ids),'prior_scene_exclusions':len(exclusions),
            'all_revision_and_stale_input_scenes_disjoint_between_episodes_and_splits':True,
            'note':'Repeated states within a single episode are allowed. Signature ignores event order and temporal edges.'}
