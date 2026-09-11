import copy,hashlib
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import to_meaning
from ss_revision.runtime import complete
from ss_revision.context import scope_key,address
from ss_retention.context import domain
from .revision_cases import fresh
from .oracle import localize,scored

def signal_hash(model,packet):return hashlib.sha256(model.vector(packet).astype('<c16').tobytes()).hexdigest()

def query(model,memory,case,stage=4,mode='missing',outputs=True):
    o=fresh(case,stage,mode);scope=copy.deepcopy(case['scope'])
    if mode=='other_episode':scope['episode']+='/other'
    if mode=='changed_fixed':
        target=next(t for t in o['cells'] if t not in scope['mutable'] and t.endswith('/polarity'))
        v=o['cells'][target]['candidates'][0];o['cells'][target]={'state':'known','candidates':['polarity:negative' if v=='polarity:positive' else 'polarity:positive']}
    p=model.encode(o);before=digest(p);fp=memory.fingerprint;r=complete(model,memory,scope,p)
    assert digest(p)==before and memory.fingerprint==fp
    result={'case_id':case['id'],'stage':stage+1,'mode':mode,'status':r['status'],'completion':{k:v for k,v in r.items() if k!='packet'},
            'source_signal_sha256':signal_hash(model,p),'correct':False,'wrong':False,'old_value_reappearance':False,
            'non_target_changed':False,'outputs':[],'input_and_memory_unchanged':True}
    if 'packet' in r:
        actual=model.recover(r['packet'])['observation'];expected=case['steps'][stage]['known']
        result.update(final_observation=actual,completed_signal_sha256=signal_hash(model,r['packet']),correct=actual==expected,wrong=actual!=expected)
        result['non_target_changed']=any(actual['cells'][t]!=c for t,c in o['cells'].items() if c['state']=='known')
        result['old_value_reappearance']=any(actual['cells'][t]!=expected['cells'][t] and actual['cells'][t]['candidates'][0] in case['history_values'][t] for t in scope['mutable'])
        if outputs:
            meaning=to_meaning(expected,model.codec.candidates);n=expected['count']
            for order,goals in (('preserve',['subject']*n),('reverse',['object' if i%2==0 else 'subject' for i in range(n)])):
                g=model.generate(r['packet'],order,goals);score=None;reread=False
                if g['status']=='generated':
                    ids=meaning['presentation'][::-1] if order=='reverse' else meaning['presentation'];truth=localize(meaning,ids,goals)
                    score=scored(truth,g['text']);back=model.document.read(g['text'])
                    if back['status']=='read':
                        m=model.document.recover(back['packet'])['meaning'];again=localize(m,m['presentation'],goals)
                        reread=again['events']==truth['events'] and again['relations']==truth['relations']
                result['outputs'].append({'order':order,'goals':goals,'generation':{k:v for k,v in g.items() if k!='link_audit'},'score':score,'reread_equal':reread})
    if mode in ('other_episode','changed_fixed'):
        newroot,_=scope_key(scope,o);oldroot,_=scope_key(case['scope'],case['final'])
        result['raw_unregistered_support']=[]
        for t in scope['mutable']:
            revision=memory.roots[oldroot]['versions'][t]
            k=address(memory.policy,newroot,t,revision,scope,o)
            result['raw_unregistered_support'].append({'target':t,'diagnostic_assumed_revision':revision,
                    'raw':{name:part.recall(k,domain(t)) for name,part in memory.ss.parts.items()}})
    return result
