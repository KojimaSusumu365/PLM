"""External-teacher-only SS error updates, separate from inference."""
import numpy as np
from plm_l1_v09.component.algebra import require
from ss_partial.update import apply
from .context import key,domain

def prepare(model,episode,packet,message,protect=True):
    require(type(protect) is bool,'protection_flag')
    rec=model.recover(packet);require(rec['status']=='recovered','teacher_source_unreadable')
    target=message.get('target');require(target in rec['observation']['cells'],'teacher_target')
    require(all(c['state']=='known' for k,c in rec['observation']['cells'].items() if k!=target),'complete_non_target_context_required')
    result=apply(model,packet,message)
    require(result['status'] in ('updated','unchanged') and result['audit']['new']['state']=='known','external_confirmation_required')
    return {'key':key(episode,rec['observation'],target),'domain':domain(target),'value':result['audit']['new']['candidates'][0],
            'protect':protect},result

def learn(memory,teacher):
    require(type(teacher) is dict and set(teacher)=={'key','domain','value','protect'},'teacher_record')
    label=(teacher['domain'],teacher['value']);require(label in memory.labels and type(teacher['protect']) is bool,'teacher_label')
    index=memory.labels.index(label)
    staged=[]
    for name,part in memory.parts.items():
        if name=='protected' and not teacher['protect']:continue
        c=part.context(teacher['key']);scores=part.scores(teacher['key'])
        error=-scores.mean(axis=0);error[index]+=1.
        delta=np.einsum('l,kld,kd->kd',error,part.values,c,optimize=False) if part.kind=='pair' else error[None,:,None]*c[:,None,:]
        new=part.weights+delta
        require(np.isfinite(new).all(),'nonfinite_update');staged.append((part,new))
    for part,new in staged:
        part.weights=new;part.registry.add(teacher['key']);part.updates+=1
    return {'status':'learned' if staged else 'not_stored','updated_parts':len(staged),'eligible_for_inference':False}

def teach(model,memory,episode,packet,message,protect=True):
    prepared,result=prepare(model,episode,packet,message,protect)
    receipt=learn(memory,prepared)
    return {'status':'confirmed','local_update':result,'memory_update':receipt,'eligible_for_inference':False}
