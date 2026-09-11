"""Read-only pending check and inherited waveform generation; no learner import."""
from bridge.runtime import receive
from ss_core.memory import WaveRevisionView
from ss_core.clock import ExactPort
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate
from .store import scope_id

def pending_result():
    return {'status':'needs_confirmation','reason':'previous_teacher_transaction_held',
            'eligible_for_inference':False,'pending_ledger_contains_no_answer_values':True}

def generate_packet(model,store,scope,packet,order='preserve',goals=None,port_factory=ExactPort,chunk=37):
    if scope_id(scope) in store.pending:return pending_result()
    try:
        rec=model.recover(packet)
        if rec['status']!='recovered' or rec['observation']['count']!=2:raise ValueError('two_event_packet_required')
        view=WaveRevisionView(store.memory,port_factory,chunk)
        session=Session(model,view,scope,packet)
        r=generate(model,view,session,order=order,goals=goals)
        return {**r,'fresh_session_no_receipts':not session.confirmed,'memory_windows':view.ss.traces}
    except (ValueError,TypeError,OverflowError) as e:
        return {'status':'abstain','reason':str(e),'eligible_for_inference':False}

def generate_received(model,store,scope,wire,message_id,mode='spread',order='preserve',goals=None,chunk=37):
    if scope_id(scope) in store.pending:return pending_result()
    r=receive(model,wire,message_id,mode)
    if r['status']!='received':return r
    return {**generate_packet(model,store,scope,r['packet'],order,goals,chunk=chunk),
            'reception':{k:v for k,v in r.items() if k!='packet'}}
