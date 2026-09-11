"""Read-only receive and cold generation. No simulator, evaluator or teacher import."""
import hashlib
from .carrier import demodulate
from .recovery import recover_masked
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate

def signal_sha(vector):return hashlib.sha256(vector.astype('<c16').tobytes()).hexdigest()

def receive(model,wire,message_id,mode='spread'):
    try:
        vector,mask,frames=demodulate(model,wire,message_id,mode)
        base={'frames':frames,'despread_signal_sha256':signal_sha(vector),'observed_components':int(mask.sum()),'eligible_for_inference':False}
        if any(f['sync']['status']!='aligned' for f in frames):return dict(base,status='abstain',stage='synchronization',reason='at_least_one_frame_unaligned')
        try:packet,audit=recover_masked(model,vector,mask)
        except (ValueError,TypeError,OverflowError) as e:return dict(base,status='abstain',stage='meaning_recovery',reason=str(e))
        return dict(base,status='received',stage='ready',packet=packet,recovery=audit,recovered_signal_sha256=signal_sha(model.vector(packet)))
    except (ValueError,TypeError,OverflowError) as e:return {'status':'rejected','stage':'contract','reason':str(e),'eligible_for_inference':False}

def generate_received(model,memory,scope,wire,message_id,mode='spread',order='preserve',goals=None):
    result=receive(model,wire,message_id,mode)
    if result['status']!='received':return result
    try:
        session=Session(model,memory,scope,result['packet']);g=generate(model,memory,session,order=order,goals=goals)
        return {**g,'bridge_stage':'generation','reception':{k:v for k,v in result.items() if k!='packet'},
                'fresh_session_no_receipts':not session.confirmed}
    except (ValueError,TypeError,OverflowError) as e:return {'status':'abstain','stage':'memory_scope','reason':str(e),'eligible_for_inference':False}
