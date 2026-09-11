from plm_l1_v09.component.algebra import require
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import assess
from ss_reconfirm.learning import confirm
from .runtime import candidates

def answer(model,memory,workset,question,value,excluded=()):
    require(type(question) is dict and any(r['question']==question for r in candidates(memory,workset,excluded)),'stale_or_unrequested_question')
    e=next(e for e in workset.entries if e['id']==question['id']);session=Session(model,memory,e['scope'],e['packet'])
    q=next(q for q in assess(model,memory,session,'always')['questions'] if q['target']==question['target'])
    # An explicit maintenance confirmation is valid even when the current SS answer is strong.
    new,receipt=confirm(model,memory,session,q,value,'always')
    require(new.confirmed=={question['target']:receipt['revision']},'one_external_confirmation')
    # Do not return or retain the confirmed packet as future recall evidence.
    return {**receipt,'id':question['id'],'required_now':question['required_now'],'confirmed_packet_discarded':True}
