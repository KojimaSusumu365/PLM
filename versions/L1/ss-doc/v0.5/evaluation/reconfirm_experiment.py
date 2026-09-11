import copy,hashlib
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import to_meaning,cell
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import assess,complete
from ss_reconfirm.learning import confirm
from .reconfirm_cases import observation
from .oracle import localize,scored

def signal_hash(model,packet):return hashlib.sha256(model.vector(packet).astype('<c16').tobytes()).hexdigest()

def finish(model,memory,session,truth,policy,outputs=True):
    fp=memory.fingerprint;before=digest(session.payload());r=complete(model,memory,session,policy)
    row={'status':r['status'],'correct':False,'wrong':False,'nonmutable_changed':False,'known_changed_by_ss':False,
         'pending_targets':[q['target'] for q in r.get('questions',[])],
         'completion':{k:v for k,v in r.items() if k!='packet'},'outputs':[],'session_confirmed_targets':dict(session.confirmed)}
    packet=r.get('packet')
    if packet is not None:
        actual=model.recover(packet)['observation'];original=model.recover(session.packet)['observation']
        row.update(correct=actual==truth,wrong=actual!=truth,final_observation=actual,completed_signal_sha256=signal_hash(model,packet))
        row['nonmutable_changed']=any(actual['cells'][t]!=c for t,c in original['cells'].items() if t not in session.scope['mutable'])
        row['known_changed_by_ss']=any(actual['cells'][t]!=c for t,c in original['cells'].items() if c['state']=='known')
        if outputs:
            meaning=to_meaning(truth,model.codec.candidates);n=truth['count']
            for order,goals in (('preserve',['subject']*n),('reverse',['object' if i%2==0 else 'subject' for i in range(n)])):
                g=model.generate(packet,order,goals);score=None;reread=False
                if g['status']=='generated':
                    ids=meaning['presentation'][::-1] if order=='reverse' else meaning['presentation'];expected=localize(meaning,ids,goals)
                    score=scored(expected,g['text']);back=model.document.read(g['text'])
                    if back['status']=='read':
                        m=model.document.recover(back['packet'])['meaning'];got=localize(m,m['presentation'],goals)
                        reread=got['events']==expected['events'] and got['relations']==expected['relations']
                row['outputs'].append({'order':order,'goals':goals,'generation':{k:v for k,v in g.items() if k!='link_audit'},'score':score,'reread_equal':reread})
    assert memory.fingerprint==fp and digest(session.payload())==before
    return row,packet

def episode(model,memory,case,policy,remaining,outputs=True):
    packet=model.encode(observation(case));session=Session(model,memory,case['scope'],packet)
    initial=assess(model,memory,session,policy);plan=initial;answers=[]
    while plan['status']=='needs_confirmation' and len(answers)<remaining:
        q=plan['questions'][0]
        # Evaluator-only external teacher. The policy sees neither this table nor hidden truth.
        value=case['final']['cells'][q['target']]['candidates'][0]
        session,receipt=confirm(model,memory,session,q,value,policy);answers.append({'question':q,'external_value':value,'receipt':receipt})
        assert len(answers)<=len(case['scope']['mutable'])
        plan=assess(model,memory,session,policy)
    result,_=finish(model,memory,session,case['final'],policy,outputs)
    return {'case_id':case['id'],'query_kind':case['query_kind'],'source_signal_sha256':signal_hash(model,packet),
            'initial_plan':initial,'answers':answers,'confirmations_used':len(answers),'budget_remaining_before':remaining,
            'budget_exhausted_while_pending':plan['status']=='needs_confirmation' and len(answers)==remaining,
            'final':result}

def probe(model,memory,case,outputs=True):
    o=observation(case,'missing');packet=model.encode(o);session=Session(model,memory,case['scope'],packet)
    result,completed=finish(model,memory,session,case['final'],'ss_selective',outputs)
    assert not session.confirmed
    return {'case_id':case['id'],'source_signal_sha256':signal_hash(model,packet),'no_session_receipts':True,**result},packet,completed

def failure_regression(model):
    from ss_revision.memory import RevisionMemory
    from .integrity import ROOT,read
    rows=[]
    for f in read(ROOT/'data/V04_FAILURE_FIXTURES.json'):
        m=RevisionMemory.load(ROOT/'data/v04_failure_memories'/f['condition'],model.codec.candidates)
        p=model.encode(f['observation']);s=Session(model,m,f['scope'],p)
        legacy,_=finish(model,m,s,f['truth'],'legacy');assert legacy['wrong']
        before=assess(model,m,s,'ss_selective');assert before['status']=='needs_confirmation'
        answers=[]
        while len(answers)<2:
            plan=assess(model,m,s,'ss_selective')
            if plan['status']=='ready':break
            q=plan['questions'][0];s,r=confirm(model,m,s,q,f['truth']['cells'][q['target']]['candidates'][0]);answers.append(r)
        final,_=finish(model,m,s,f['truth'],'ss_selective');assert final['correct']
        o=copy.deepcopy(f['truth'])
        for t in f['scope']['mutable']:o['cells'][t]=cell('unobserved',[])
        cold,_=finish(model,m,Session(model,m,f['scope'],model.encode(o)),f['truth'],'ss_selective')
        rows.append({'case_id':f['case_id'],'source_condition':f['condition'],'legacy':legacy,'selective_before':before,
                     'answers':answers,'selective_after':final,'cold_without_receipts':cold})
    return rows
