import random
from .integrity import ROOT,read
from .cases import dataset as pool
from .reconfirm_cases import make_case,footprint,observation

SIZES=(('development',6,96),('500',12,320),('501',12,320),('400',12,320),('401',12,320))

def build(exclusions):
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];used=set(exclusions);splits={};construction=[]
    for split,focal,background in SIZES:
        accepted=[];batch=0;rejected=0
        while len(accepted)<focal+background:
            for source in pool('ssdoc06/'+split+'/'+str(batch)):
                i=len(accepted)
                if i>=focal+background:break
                n=2+(i//6)%2 if i<focal else 2+i%2
                if source['known']['count']!=n:continue
                c=make_case(source,i,split,i<focal,lex);c['id']='d06-'+c['id'];keys=footprint(c,lex)
                if keys&used:rejected+=1;continue
                accepted.append(c);used.update(keys)
            batch+=1;assert batch<24
        order=list(range(focal));random.Random('delay06/order/'+split).shuffle(order)
        splits[split]={'cases':accepted,'order':order,'focal':focal,'background':background}
        construction.append({'split':split,'collision_rejections':rejected,'batches':batch})
    return {'schema':'plm-delayed-selection-corpus-06','splits':splits,'construction':construction,
            'selector_training_splits':['500','501'],'evaluation_splits':['400','401'],'development_split':'development'}

def audit(data,exclusions):
    seen=set(exclusions);ids=set();rows=[];lex=read(ROOT/'data/lexicon.json')['slot_candidates']
    for split,ds in sorted(data['splits'].items()):
        count=0
        for c in ds['cases']:
            assert c['scope']['episode'] not in ids;ids.add(c['scope']['episode']);keys=footprint(c,lex)
            assert not keys&seen;seen.update(keys);count+=len(keys)
        rows.append({'split':split,'episodes':len(ds['cases']),'scene_fingerprints':count})
    return {'passed':True,'episodes':len(ids),'rows':rows,'prior_scene_exclusions':len(exclusions),
            'all_initial_revision_and_stale_scenes_disjoint_between_episodes_and_splits':True,
            'signature':'sorted events without IDs, presentation, temporal edges; repeated states within an episode allowed'}

def entries(model,cases):return [{'id':c['id'],'scope':c['scope'],'packet':model.encode(observation(c,'missing'))} for c in cases]
