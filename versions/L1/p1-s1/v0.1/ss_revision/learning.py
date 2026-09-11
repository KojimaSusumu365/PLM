"""Explicit confirmation transactions. Revision numbers are not truth authentication."""
from plm_l1_v09.component.algebra import digest,require
from ss_partial.update import apply,request as local_request
from ss_retention.context import domain,key as legacy_key
from ss_retention.learning import learn as ss_learn
from .context import scope_key,address,hexadecimal

FIELDS={'schema','scope_sha256','packet_sha256','target','base_revision','revision','value','operation'}
PREPARED={'root','target','base_revision','revision','value','legacy_key'}

def begin(model,memory,scope,packet,protect=True):
    rec=model.recover(packet);require(rec['status']=='recovered','source_unreadable')
    root,targets=scope_key(scope,rec['observation']);memory.register(root,targets,protect)
    return root

def request(model,memory,scope,packet,target,value,operation='supply'):
    rec=model.recover(packet);require(rec['status']=='recovered','source_unreadable')
    root,_=scope_key(scope,rec['observation']);require(root in memory.roots and target in memory.roots[root]['versions'],'unregistered_target')
    base=memory.roots[root]['versions'][target]
    return {'schema':'plm-ss-revision-confirmation-04','scope_sha256':root,'packet_sha256':digest(packet),
            'target':target,'base_revision':base,'revision':base+1,'value':value,'operation':operation}

def prepare(model,memory,scope,packet,message):
    require(type(message) is dict and set(message)==FIELDS and message['schema']=='plm-ss-revision-confirmation-04','confirmation_contract')
    rec=model.recover(packet);require(rec['status']=='recovered','source_unreadable')
    root,targets=scope_key(scope,rec['observation']);target=message['target']
    require(message['scope_sha256']==root and root in memory.roots and target in targets,'confirmation_scope')
    require(type(message['base_revision']) is int and type(message['revision']) is int,'revision_integer')
    require(message['base_revision']==memory.roots[root]['versions'][target] and message['revision']==message['base_revision']+1,'stale_or_out_of_order_confirmation')
    require(message['packet_sha256']==digest(packet),'stale_or_wrong_packet')
    result=apply(model,packet,local_request(packet,target,message['value'],message['operation']))
    require(result['status'] in ('updated','unchanged') and result['audit']['new']['state']=='known','explicit_confirmation_required')
    teacher={'root':root,'target':target,'base_revision':message['base_revision'],'revision':message['revision'],
             'value':result['audit']['new']['candidates'][0],'legacy_key':legacy_key(scope['episode'],rec['observation'],target)}
    return teacher,result

def learn(memory,teacher):
    # Internal prepared-record API; public teach() first validates numeric packet and confirmation.
    require(type(teacher) is dict and set(teacher)==PREPARED,'prepared_fields')
    root,target=teacher['root'],teacher['target']
    require(hexadecimal(root) and root in memory.roots and target in memory.roots[root]['versions'],'prepared_scope')
    state=memory.roots[root];base=teacher['base_revision'];revision=teacher['revision']
    require(type(base) is int and type(revision) is int and base==state['versions'][target] and revision==base+1 and revision<=1000000,'stale_or_out_of_order_confirmation')
    require(hexadecimal(teacher['legacy_key']),'legacy_key_contract')
    k=address(memory.policy,root,target,revision,prepared_legacy=teacher['legacy_key'])
    # The inherited SS updater stages all channel updates before committing any coefficients.
    receipt=ss_learn(memory.ss,{'key':k,'domain':domain(target),'value':teacher['value'],'protect':state['protect']})
    state['versions'][target]=revision
    return {'status':'confirmed','root':root,'target':target,'revision':revision,'memory_update':receipt,'eligible_for_inference':False}

def teach(model,memory,scope,packet,message):
    teacher,local=prepare(model,memory,scope,packet,message);receipt=learn(memory,teacher)
    return {**receipt,'packet':local['packet'],'local_audit':local['audit']}
