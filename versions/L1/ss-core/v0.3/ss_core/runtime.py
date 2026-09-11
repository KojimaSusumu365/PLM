"""Cold generation from a waveform-scanned SS memory; no teacher API imports."""
from bridge.runtime import receive
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate
from .clock import ExactPort
from .memory import WaveRevisionView


def generate_received(model, memory, scope, wire, message_id, mode='spread', order='preserve', goals=None,
                      port_factory=ExactPort, chunk=1):
    reception = receive(model, wire, message_id, mode)
    if reception['status'] != 'received':
        return reception
    try:
        if model.recover(reception['packet'])['observation']['count'] != 2 or len(scope['mutable']) != 2:
            raise ValueError('two_events_two_targets')
        view = WaveRevisionView(memory, port_factory, chunk)
        session = Session(model, view, scope, reception['packet'])
        result = generate(model, view, session, order=order, goals=goals)
        return {**result, 'memory_windows':view.ss.traces, 'fresh_session_no_receipts':not session.confirmed,
                'reception':{k:v for k,v in reception.items() if k != 'packet'}}
    except (ValueError, TypeError, OverflowError) as e:
        return {'status':'abstain', 'stage':'memory_scope', 'reason':str(e), 'eligible_for_inference':False}
