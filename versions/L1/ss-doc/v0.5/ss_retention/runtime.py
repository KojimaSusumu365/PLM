"""Requery inference: never imports retention learning, reader or an evaluator."""
import copy
from plm_l1_v09.component.algebra import digest,require
from ss_partial.update import apply,request
from .context import key,domain

def complete(model,memory,episode,packet):
    try:
        rec=model.recover(packet);require(rec['status']=='recovered',rec.get('reason','unreadable'))
        o=rec['observation'];audit=[];fills=[]
        for target,c in o['cells'].items():
            k=key(episode,o,target)
            if c['state']=='known' and not memory.registered(k):continue
            if c['state']=='conflict':return {'status':'needs_information','reason':'explicit_conflict','target':target,'audit':audit,'eligible_for_inference':False}
            r=memory.recall(k,domain(target));audit.append({'target':target,'key':k,'recall':r})
            if c['state']=='known':
                if r['value'] is not None and r['value']!=c['candidates'][0]:
                    return {'status':'needs_information','reason':'new_explicit_information_disagrees','target':target,'audit':audit,'eligible_for_inference':False}
                continue
            if r['value'] is None:return {'status':'needs_information','reason':r['status'],'target':target,'audit':audit,'eligible_for_inference':False}
            if c['state']=='ambiguous' and r['value'] not in c['candidates']:
                return {'status':'needs_information','reason':'memory_outside_current_candidates','target':target,'audit':audit,'eligible_for_inference':False}
            fills.append((target,r['value']))
        current=copy.deepcopy(packet);changes=[]
        for target,value in fills:
            result=apply(model,current,request(current,target,value))
            require(result['status'] in ('updated','unchanged'),'memory_completion_failed')
            current=result['packet'];changes.append(result['audit'])
        final=model.recover(current);require(final['status']=='recovered' and not final['pending'],'incomplete_reconstruction')
        return {'status':'completed','packet':current,'audit':audit,'changes':changes,
                'source':'retained_external_confirmation' if fills else 'current_explicit_observation',
                'source_packet_unchanged':True,'eligible_for_inference':False}
    except (ValueError,TypeError,OverflowError) as e:return {'status':'abstain','reason':str(e),'eligible_for_inference':False}

def generate(model,memory,episode,packet,order='preserve',goals=None):
    result=complete(model,memory,episode,packet)
    if result['status']!='completed':return result
    g=model.generate(result['packet'],order,goals)
    return {**g,'retention_audit':result['audit'],'changes':result['changes'],'source':result['source']}
