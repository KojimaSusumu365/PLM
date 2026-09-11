"""Explicit external-teacher ingress. Values are recovered from chips, not a truth API.

Calling this API declares the received document a teacher. It does not authenticate
the sender or verify truth. Updates are staged on a copied memory, then returned.
"""
import copy
from plm_l1_v09.component.algebra import require
from ss_revision.learning import begin,request,teach
from .runtime import receive

def learn_packet(model,memory,scope,packet):
    """Internal transaction primitive; public ingress below first receives the chips."""
    rec=model.recover(packet);require(rec['status']=='recovered' and not rec['pending'],'teacher_must_be_complete')
    staged=copy.deepcopy(memory);root=begin(model,staged,scope,packet);current=packet;receipts=[]
    for target in scope['mutable']:
        value=rec['observation']['cells'][target]['candidates'][0]
        message=request(model,staged,scope,current,target,value,'supply')
        receipt=teach(model,staged,scope,current,message);current=receipt['packet']
        receipts.append({k:v for k,v in receipt.items() if k!='packet'})
    return staged,{'status':'learned','root':root,'values_recovered_from_received_signal':True,'receipts':receipts,'received_observation':rec['observation'],
                   'before_memory':memory.fingerprint,'after_memory':staged.fingerprint,'eligible_for_inference':False}

def learn_received(model,memory,scope,wire,message_id,mode='spread'):
    reception=receive(model,wire,message_id,mode)
    if reception['status']!='received':return memory,reception
    try:
        updated,result=learn_packet(model,memory,scope,reception['packet'])
        return updated,{**result,'reception':{k:v for k,v in reception.items() if k!='packet'}}
    except (ValueError,TypeError,OverflowError) as e:return memory,{'status':'rejected','stage':'teacher_contract','reason':str(e),'eligible_for_inference':False}
