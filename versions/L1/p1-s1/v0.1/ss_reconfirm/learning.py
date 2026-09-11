"""One explicit external answer advances a session and the persistent SS memory."""
from plm_l1_v09.component.algebra import require
from ss_revision.learning import request,teach
from .session import Session
from .runtime import assess

def confirm(model,memory,session,question,value,policy='ss_selective'):
    observation,_=session.validate(model,memory);plan=assess(model,memory,session,policy)
    require(plan['status']=='needs_confirmation' and type(question) is dict and question in plan['questions'],'stale_or_unrequested_confirmation')
    target=question['target'];state=observation['cells'][target]['state']
    operation='revise' if state=='known' else 'resolve' if state=='conflict' else 'supply'
    message=request(model,memory,session.scope,session.packet,target,value,operation)
    result=teach(model,memory,session.scope,session.packet,message)
    new=Session(model,memory,session.scope,result['packet']);new.confirmed={**session.confirmed,target:result['revision']};new.validate(model,memory)
    return new,{'status':'confirmed','target':target,'revision':result['revision'],'local_audit':result['local_audit'],
                'memory_fingerprint':memory.fingerprint,'eligible_for_inference':False}
