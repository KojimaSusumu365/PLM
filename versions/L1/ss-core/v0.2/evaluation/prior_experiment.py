import copy
from plm_l1_v09.component.algebra import digest
from ss_revision.memory import RevisionMemory
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import complete
from bridge.carrier import encode,budget
from bridge.runtime import receive,signal_sha
from bridge.learning import learn_received,learn_packet
from .channel import channel,control_receive,synchronization_errors
from .oracle import localize,scored

def compact(value):
    if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if k not in ('packet','chips_per_coordinate','correlation_decisions')}
    if isinstance(value,list):return [compact(v) for v in value]
    return value

def finish(model,memory,scope,reception,case):
    base={'status':'held','failure_stage':reception.get('stage'),'correct':False,'wrong':False,'outputs':[],
          'requested_outputs':2,'fresh_session_no_receipts':True,'nonmutable_changed':False}
    if reception['status']!='received':return base
    try:
        original=model.recover(reception['packet']);base['received_observation_equal']=original['observation']==case['query']
        session=Session(model,memory,scope,reception['packet']);before=memory.fingerprint;r=complete(model,memory,session)
        base['completion']=compact(r);assert not session.confirmed
        if r['status']!='completed':return dict(base,failure_stage='memory_completion')
        actual=model.recover(r['packet'])['observation'];n=case['known']['count'];base['final_observation']=actual
        base['nonmutable_changed']=any(actual['cells'][t]!=v for t,v in original['observation']['cells'].items() if t not in scope['mutable'])
        base['completed_signal_sha256']=signal_sha(model.vector(r['packet']))
        for order,goals in (('preserve',['subject']*n),('reverse',['object' if i%2==0 else 'subject' for i in range(n)])):
            g=model.generate(r['packet'],order,goals);score=None;back_equal=False
            if g['status']=='generated':
                ids=case['meaning']['presentation'][::-1] if order=='reverse' else case['meaning']['presentation'];expected=localize(case['meaning'],ids,goals)
                score=scored(expected,g['text']);back=model.document.read(g['text'])
                if back['status']=='read':
                    m=model.document.recover(back['packet'])['meaning'];got=localize(m,m['presentation'],goals)
                    back_equal=got['events']==expected['events'] and got['relations']==expected['relations']
            base['outputs'].append({'order':order,'goals':goals,'generation':{k:v for k,v in g.items() if k!='link_audit'},'score':score,'reread_equal':back_equal})
        success=all(o['generation']['status']=='generated' for o in base['outputs'])
        correct=success and actual==case['known'] and all(all(o['score'].values()) and o['reread_equal'] for o in base['outputs'])
        wrong=any(o['generation']['status']=='generated' and (not all(o['score'].values()) or not o['reread_equal']) for o in base['outputs'])
        assert memory.fingerprint==before
        return dict(base,status='generated' if success else 'held',failure_stage=None if success else 'generation',correct=correct,wrong=wrong)
    except (ValueError,TypeError,OverflowError) as e:return dict(base,failure_stage='memory_scope',reason=str(e))

def run_case(model,case,condition,seed,method,out):
    mode='repeat' if method=='repeat_estimated' else 'spread';ids=[case['id']+'/teacher',case['id']+'/query']
    packets=[model.encode(case['known']),model.encode(case['query'])];memory=RevisionMemory(model.codec.candidates,'versioned_pair','bridge-memory-'+str(seed))
    receipts=[];wires=[];truths=[]
    if method=='direct':
        memory,teacher=learn_packet(model,memory,case['scope'],packets[0]);teacher['values_recovered_from_received_signal']=False
        query={'status':'received','stage':'ready','packet':packets[1],'direct_reference':True};teacher_reception={}
    else:
        for j,p in enumerate(packets):
            tx=encode(model,p,ids[j],mode);wire,truth=channel(model,tx,condition,seed+10000*j);wires.append(wire);truths.append(truth)
        if method in ('ss_estimated','repeat_estimated'):
            memory,teacher=learn_received(model,memory,case['scope'],wires[0],ids[0],mode)
            teacher_reception=teacher.get('reception',teacher);query=receive(model,wires[1],ids[1],mode)
        else:
            teacher_reception=control_receive(model,wires[0],ids[0],method,truths[0])
            if teacher_reception['status']=='received':
                try:memory,teacher=learn_packet(model,memory,case['scope'],teacher_reception['packet'])
                except (ValueError,TypeError) as e:teacher={'status':'rejected','reason':str(e)}
            else:teacher=teacher_reception
            query=control_receive(model,wires[1],ids[1],method,truths[1])
    memory.save(out/'memory');cold=RevisionMemory.load(out/'memory',model.codec.candidates);assert cold.fingerprint==memory.fingerprint
    result=finish(model,cold,case['scope'],query,case)
    row={'case_id':case['id'],'count':case['known']['count'],'condition':condition,'channel_seed':seed,'method':method,
         'teacher':compact(teacher),'teacher_learned':teacher['status']=='learned',
         'teacher_correct':teacher.get('received_observation')==case['known'] if teacher['status']=='learned' else None,
         'query':compact(query),'result':result,'memory_fingerprint':cold.fingerprint,'cost':budget() if method!='direct' else {'total_chips':0,'reference_without_channel':True},
         'teacher_wire_sha256':digest(wires[0]) if wires else None,'query_wire_sha256':digest(wires[1]) if wires else None,
         'teacher_sync':synchronization_errors(teacher_reception,truths[0]) if truths else None,
         'query_sync':synchronization_errors(query,truths[1]) if truths else None,'eligible_for_inference':False}
    return row
