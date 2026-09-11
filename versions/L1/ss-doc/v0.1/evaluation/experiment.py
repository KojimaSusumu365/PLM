"""All external gold and grammar live here, outside runtime."""
import copy
import hashlib
import math
import numpy as np
from plm_l1_v09.component.algebra import canonical
from ss_document.contract import IDS,edge
from .oracle import localize,scored


def vector(packet):
    v=np.asarray(packet['real'],float).astype(complex);v.imag=np.asarray(packet['imag'],float);return v


def signal_hash(packet):return hashlib.sha256(vector(packet).astype('<c16').tobytes()).hexdigest()


def semantic(meaning):
    m=localize(meaning,meaning['presentation'],['subject']*len(meaning['events']))
    return {k:m[k] for k in ('events','relations')}


def adapt_legacy(m):
    rename=dict(zip(m['presentation'],IDS[:2]));events=[]
    for old in m['presentation']:
        e=next(e for e in m['events'] if e['id']==old);events.append({**e,'id':rename[old]})
    t=m['temporal'];r=edge(*IDS[:2]) if t['kind']=='unknown' else edge(*IDS[:2],rename[t['source']],rename[t['target']])
    return {'events':events,'presentation':list(IDS[:2]),'relations':[r]}


def generation(model,packet,meaning,order,goals):
    ids=meaning['presentation'] if order=='preserve' else list(reversed(meaning['presentation']))
    expected=localize(meaning,ids,goals);out=model.generate(packet,order,goals)
    result={'order':order,'goals':list(goals),'generation':out}
    if out['status']=='generated':
        result['score']=scored(expected,out['text']);rr=model.read(out['text'])
        if rr['status']=='read':
            rec=model.recover(rr['packet']);want={k:expected[k] for k in ('events','relations')}
            result['reread']={'status':'read','semantic_equal':rec['status']=='recovered' and semantic(rec['meaning'])==want,
                              'signal_sha256':signal_hash(rr['packet']),'recovered':rec}
        else:result['reread']={'status':rr['status'],'semantic_equal':False,'reason':rr.get('reason')}
    else:result['score']=None;result['reread']={'status':'not_run','semantic_equal':False}
    return result


def trial(model,case,full=True):
    meaning=case['meaning'];n=len(meaning['events']);read=model.read(case['text'])
    direct=model.encode(meaning);arrays={'direct':vector(direct)}
    r={'case_id':case['id'],'count':n,'read_status':read['status'],'read_reason':read.get('reason'),'read_semantic_equal':False,
       'direct_signal_sha256':signal_hash(direct),'outputs':[]}
    if read['status']=='read':
        recovered=model.recover(read['packet']);r['read_recovered']=recovered
        r['read_semantic_equal']=recovered['status']=='recovered' and semantic(recovered['meaning'])==semantic(meaning)
        r['read_signal_sha256']=signal_hash(read['packet']);arrays['read']=vector(read['packet'])
    configs=[('preserve',['subject']*n)]
    if full:
        configs=[(order,goals) for order in ('preserve','reverse') for goals in
                 (['subject']*n,['object']*n,[('subject','object')[i%2] for i in range(n)])]
    for order,goals in configs:
        if read['status']=='read':r['outputs'].append(generation(model,read['packet'],meaning,order,goals))
        else:r['outputs'].append({'order':order,'goals':goals,'generation':{'status':'not_run','reason':'reader_abstained'},
                                  'score':None,'reread':{'status':'not_run','semantic_equal':False}})
    r['direct_generation']=generation(model,direct,meaning,'reverse',['subject']*n)
    return r,arrays


def disturbances(model,meaning,seed):
    c=model.codec;clean=c.encode(meaning);parts={};rng=np.random.default_rng(seed)
    parts['zero']=np.zeros_like(clean)
    missing=c.presence[2].copy()
    for role in c.candidates:missing+=c.events[2][role][c.candidates[role].index(meaning['events'][2][role])]
    parts['missing_event']=clean-missing/math.sqrt(3.)
    old=meaning['events'][1]['subject'];new=next(v for v in c.candidates['subject'] if v!=old and v!=meaning['events'][1]['object'])
    parts['competing_subject']=clean+c.events[1]['subject'][c.candidates['subject'].index(new)]/math.sqrt(3.)
    parts['half_erasure']=clean*np.tile([1.,0.],c.dimension//2)
    parts['strong_noise']=clean+2.*(rng.normal(size=c.dimension)+1j*rng.normal(size=c.dimension))
    edited=copy.deepcopy(meaning);edited['events'][1]['subject']=new
    parts['clean_subject_edit']=clean+(c.events[1]['subject'][c.candidates['subject'].index(new)]-c.events[1]['subject'][c.candidates['subject'].index(old)])/math.sqrt(3.)
    # This explicit edit teaches no model and adds no text/JSON to the transmitted packet.
    relation=copy.deepcopy(meaning);pair=(IDS[0],IDS[1]);source=relation['relations'][0]
    i=c.relation_values[pair].index(source);j=1 if i==0 else 3-i
    relation['relations'][0]=copy.deepcopy(c.relation_values[pair][j])
    parts['clean_edge_edit']=clean+(c.relations[pair][j]-c.relations[pair][i])/math.sqrt(3.)
    expected={'clean_subject_edit':edited,'clean_edge_edit':relation}
    rows=[]
    for name,v in parts.items():
        packet=model.packet(v);target=expected.get(name,meaning);rec=model.recover(packet)
        result=generation(model,packet,target,'reverse',['subject']*3)
        rows.append({'name':name,'controlled_edit':name in expected,'expected_meaning':target,'recovery':rec,
                     'recovered_expected':rec['status']=='recovered' and rec['meaning']==target,'result':result,
                     'signal_sha256':signal_hash(packet)})
    return rows,parts
