import copy
import hashlib
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import to_meaning
from ss_partial.update import request
from ss_retention.context import key,domain
from ss_retention.learning import prepare,learn
from ss_retention.runtime import complete
from .oracle import localize,scored
from .cases import fresh_observation

def numeric_hash(model,p):return hashlib.sha256(model.vector(p).astype('<c16').tobytes()).hexdigest()

def teacher_records(model,data):
    records=[]
    for c in data:
        p=model.encode(c['observation'])
        t,r=prepare(model,c['episode'],p,request(p,c['target'],c['truth']),c['kind']=='focal')
        assert model.recover(r['packet'])['observation']==c['known']
        records.append(t)
    return records

def train(memory,teachers,load):
    focal=[r for r in teachers if r['protect']];background=[r for r in teachers if not r['protect']][:load]
    for t in focal:learn(memory,t)
    immediate=[memory.recall(t['key'],t['domain']) for t in focal]
    protected_before=memory.parts['protected'].weights.copy() if 'protected' in memory.parts else None
    for _ in range(2):
        for t in background:learn(memory,t)
    protected_unchanged=None if protected_before is None else bool(__import__('numpy').array_equal(protected_before,memory.parts['protected'].weights))
    return immediate,protected_unchanged

def query(model,memory,case,mode='ambiguous',outputs=True):
    o=fresh_observation(case,mode);packet=model.encode(o);original=digest(packet)
    episode=case['episode']+'/different' if mode=='other_episode' else case['episode']
    result=complete(model,memory,episode,packet)
    row={'case_id':case['id'],'mode':mode,'episode':episode,'target':case['target'],'source_signal_sha256':numeric_hash(model,packet),
         'completion':{k:v for k,v in result.items() if k!='packet'},'input_unchanged':digest(packet)==original,
         'final_equal':False,'non_target_equal':False,'outputs':[]}
    if 'packet' in result:
        rec=model.recover(result['packet']);actual=rec.get('observation');row['final_observation']=actual
        row['completed_signal_sha256']=numeric_hash(model,result['packet'])
        expected=o if mode=='explicit_new' else case['known']
        row['final_equal']=actual==expected
        row['non_target_equal']=actual is not None and all(actual['cells'][k]==v for k,v in o['cells'].items() if k!=case['target'])
        if outputs:
            meaning=to_meaning(expected,model.codec.candidates);n=meaning['events'].__len__()
            for order,goals in (('preserve',['subject']*n),('reverse',['object' if i%2==0 else 'subject' for i in range(n)])):
                g=model.generate(result['packet'],order,goals);score=None;reread=False
                if g['status']=='generated':
                    ids=meaning['presentation'] if order=='preserve' else meaning['presentation'][::-1];truth=localize(meaning,ids,goals);score=scored(truth,g['text'])
                    again=model.document.read(g['text'])
                    if again['status']=='read':
                        rec2=model.document.recover(again['packet']);m=rec2['meaning'];v=localize(m,m['presentation'],goals)
                        reread=v['events']==truth['events'] and v['relations']==truth['relations']
                row['outputs'].append({'order':order,'goals':goals,'generation':{k:v for k,v in g.items() if k!='link_audit'},'score':score,'reread_equal':reread})
    return row

def drift_probe(model,memory,case):
    # Same observable input and memory, different evaluator-only reference. No hidden sensor.
    before=memory.fingerprint;r=query(model,memory,case,outputs=True)
    changed=copy.deepcopy(case['known']);changed['cells'][case['target']]={'state':'known','candidates':[case['alternative']]}
    samequery=r['completion']['status']=='completed'
    return {'case_id':case['id'],'unchanged_memory':before==memory.fingerprint,'same_observation_as_fixed_world':True,
            'completed':samequery,'matches_old_reference':r['final_equal'],
            'matches_new_reference':r.get('final_observation')==changed,'note':'No external change information was provided.'}
