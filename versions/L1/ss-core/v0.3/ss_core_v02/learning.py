"""No oracle reads: all update checks use waveform scores and the external teacher.

Window identifiers select a fresh acquisition; independence is NOT guaranteed by
the identifier. Shared read-path corruption and false teachers remain limitations.
"""
import copy
import numpy as np
from plm_l1_v09.component.algebra import require
from ss_core.clock import ExactPort,read_scores
from ss_core.learning import WriteWindow,acknowledge
from ss_core.memory import decision
from ss_retention.context import domain
from ss_revision.context import address,hexadecimal
from ss_revision.learning import PREPARED,begin,request,prepare
from bridge.runtime import receive

METHODS=('single','mean4','unchecked','guard')
POLICY={'pre_score_rms_max':0.15,'post_score_rms_max':0.15,
        'post_error_floor':0.15,'post_error_ratio_max':0.85,'maximum_read_windows_per_part':4}

def rms(a,b):return float(np.sqrt(np.mean((a-b)**2)))

def learn(memory,teacher,method='guard',port_factory=ExactPort,chunk=37,ack=acknowledge,before_commit=None):
    require(method in METHODS and memory.method=='split_pair','method_contract')
    require(type(teacher) is dict and set(teacher)=={'key','domain','value','protect'},'teacher_record')
    label=(teacher['domain'],teacher['value'])
    require(label in memory.labels and type(teacher['protect']) is bool,'teacher_label')
    index=memory.labels.index(label)
    original=memory.fingerprint
    staged=[]
    audits={}
    cost={'read_windows_started':0,'read_ticks_processed':0,'write_ticks_acknowledged':0}
    def result(status,reason=None):
        return {'status':status,'reason':reason,'method':method,'windows':audits,'cost':dict(cost),
                'updated_parts':len(staged) if status=='learned' else 0,'eligible_for_inference':False}
    for name,part in memory.parts.items():
        if name=='protected' and not teacher['protect']:continue
        audit={'reads':[]}
        audits[name]=audit
        def acquire(source,stage,number):
            nonce='guard02/'+name+'/'+str(part.updates)+'/'+stage+'/'+str(number)
            scores,a=read_scores(source,teacher['key'],nonce,True,port_factory,chunk)
            audit['reads'].append({'stage':stage,'number':number,**a})
            cost['read_windows_started']+=1
            cost['read_ticks_processed']+=a['ticks_received']
            return scores
        count={'single':1,'mean4':4,'unchecked':2,'guard':2}[method]
        before=[]
        for i in range(count):
            s=acquire(part,'pre',i)
            if s is None:return result('held','pre_window')
            before.append(s)
        if count>=2:
            audit['pre_score_rms']=rms(before[0],before[1])
            if method=='guard' and audit['pre_score_rms']>POLICY['pre_score_rms_max']:
                return result('held','pre_disagreement')
        scores=sum(before)/count
        error=-scores.mean(axis=0)
        error[index]+=1.
        before_error=float(np.linalg.norm(error))
        audit['before_teacher_error_l2']=before_error
        context=part.context(teacher['key'])
        writer=WriteWindow(part)
        for tick in range(part.dimension):
            delta=np.zeros(4,complex)
            for candidate in range(len(part.labels)):
                delta+=error[candidate]*part.values[:,candidate,tick]*context[:,tick]
            writer.push(tick,part.weights[:,tick]+delta,ack(name,tick))
            if writer.failure:break
        weights,wa=writer.finish()
        audit['write']=wa
        cost['write_ticks_acknowledged']+=wa['written_ticks']
        if weights is None:return result('held','write_window')
        if method in ('unchecked','guard'):
            preview=copy.copy(part)
            preview.weights=weights
            after=[]
            for i in range(2):
                s=acquire(preview,'post',i)
                if s is None:return result('held','post_window')
                after.append(s)
            post=sum(after)/2
            after_error=-post.mean(axis=0)
            after_error[index]+=1.
            audit['post_score_rms']=rms(after[0],after[1])
            audit['after_teacher_error_l2']=float(np.linalg.norm(after_error))
            audit['post_decision']=decision(part,teacher['key'],teacher['domain'],post)
            audit['checks']={
                'post_agreement':audit['post_score_rms']<=POLICY['post_score_rms_max'],
                'external_teacher_supported':audit['post_decision']['value']==teacher['value'],
                'error_reduced_or_small':audit['after_teacher_error_l2']<=max(POLICY['post_error_floor'],before_error*POLICY['post_error_ratio_max'])}
            if method=='guard' and not all(audit['checks'].values()):return result('held','post_inconsistency')
        staged.append((part,weights))
    if before_commit is not None:before_commit()
    if memory.fingerprint!=original:return result('held','stale_memory')
    for part,weights in staged:
        part.weights=weights
        part.registry.add(teacher['key'])
        part.updates+=1
    return result('learned')

def learn_revision(memory,teacher,**options):
    require(type(teacher) is dict and set(teacher)==PREPARED,'prepared_fields')
    root,target=teacher['root'],teacher['target']
    require(hexadecimal(root) and root in memory.roots and target in memory.roots[root]['versions'],'prepared_scope')
    state=memory.roots[root]
    base,revision=teacher['base_revision'],teacher['revision']
    require(type(base) is int and type(revision) is int and base==state['versions'][target] and revision==base+1 and revision<=1000000,'stale_revision')
    require(hexadecimal(teacher['legacy_key']),'legacy_key_contract')
    key=address(memory.policy,root,target,revision,prepared_legacy=teacher['legacy_key'])
    r=learn(memory.ss,{'key':key,'domain':domain(target),'value':teacher['value'],'protect':state['protect']},**options)
    if r['status']=='learned':state['versions'][target]=revision
    return {'status':'confirmed' if r['status']=='learned' else 'held','target':target,
            'revision':state['versions'][target],'memory_update':r,'eligible_for_inference':False}

def learn_packet(model,memory,scope,packet,protect=True,**options):
    rec=model.recover(packet)
    require(rec['status']=='recovered' and not rec['pending'],'teacher_must_be_complete')
    require(rec['observation']['count']==2 and len(scope['mutable'])==2,'two_events_two_targets')
    original=memory.fingerprint
    staged=copy.deepcopy(memory)
    root=begin(model,staged,scope,packet,protect)
    current=packet
    receipts=[]
    cost={'read_windows_started':0,'read_ticks_processed':0,'write_ticks_acknowledged':0}
    for target in scope['mutable']:
        value=rec['observation']['cells'][target]['candidates'][0]
        teacher,local=prepare(model,staged,scope,current,request(model,staged,scope,current,target,value))
        r=learn_revision(staged,teacher,**options)
        receipts.append(r)
        for k,v in r['memory_update']['cost'].items():cost[k]+=v
        if r['status']!='confirmed':
            return memory,{'status':'held','stage':'guarded_transaction','receipts':receipts,'cost':cost,
                'before_memory':original,'after_memory':memory.fingerprint,'eligible_for_inference':False}
        current=local['packet']
    require(memory.fingerprint==original,'original_memory_changed')
    return staged,{'status':'learned','root':root,'receipts':receipts,'cost':cost,
        'received_observation':rec['observation'],'before_memory':original,'after_memory':staged.fingerprint,'eligible_for_inference':False}

def learn_received(model,memory,scope,wire,message_id,mode='spread',protect=True,**options):
    r=receive(model,wire,message_id,mode)
    if r['status']!='received':return memory,r
    try:
        updated,result=learn_packet(model,memory,scope,r['packet'],protect,**options)
        return updated,{**result,'reception':{k:v for k,v in r.items() if k!='packet'}}
    except (ValueError,TypeError,OverflowError) as e:
        return memory,{'status':'rejected','reason':str(e),'stage':'teacher_contract','eligible_for_inference':False}
