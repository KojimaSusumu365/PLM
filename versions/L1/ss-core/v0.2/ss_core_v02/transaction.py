"""Common pending ledger for every comparison method; holds do not erase SS memory."""
from .store import Store,scope_id
from .learning import learn_packet
from bridge.runtime import receive

def apply_packet(model,store,scope,packet,protect=True,**options):
    key=scope_id(scope)
    try:
        memory,r=learn_packet(model,store.memory,scope,packet,protect,**options)
    except (ValueError,TypeError,OverflowError) as e:
        memory=store.memory
        r={'status':'rejected','reason':str(e),'eligible_for_inference':False}
    pending=set(store.pending)
    if r['status']=='learned':pending.discard(key)
    else:pending.add(key)
    updated=Store(memory,pending)
    return updated,{**r,'before_store':store.fingerprint,'after_store':updated.fingerprint,
                    'pending_scope':key if key in pending else None}

def apply_received(model,store,scope,wire,message_id,mode='spread',protect=True,**options):
    key=scope_id(scope)
    r=receive(model,wire,message_id,mode)
    if r['status']!='received':
        updated=Store(store.memory,store.pending|{key})
        return updated,{**r,'before_store':store.fingerprint,'after_store':updated.fingerprint,'pending_scope':key}
    updated,result=apply_packet(model,store,scope,r['packet'],protect,**options)
    return updated,{**result,'reception':{k:v for k,v in r.items() if k!='packet'}}
