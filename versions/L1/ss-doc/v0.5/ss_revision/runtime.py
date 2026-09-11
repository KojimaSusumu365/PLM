"""Fresh numeric observation -> current SS revision -> local completion -> language core."""
import copy
from plm_l1_v09.component.algebra import digest,require
from ss_partial.update import apply,request
from ss_retention.context import domain
from .context import scope_key,address

def hold(reason,audit=None,target=None):
    return {'status':'needs_information','reason':reason,'audit':audit or [],'target':target,'eligible_for_inference':False}

def complete(model,memory,scope,packet):
    try:
        source=digest(packet);rec=model.recover(packet)
        require(rec['status']=='recovered',rec.get('reason','source_unreadable'))
        o=rec['observation'];root,targets=scope_key(scope,o)
        if root not in memory.roots:return hold('unregistered_scope')
        versions=memory.roots[root]['versions'];require(set(versions)==set(targets),'scope_target_mismatch')
        audit=[];fills=[]
        for target in targets:
            c=o['cells'][target];revision=versions[target]
            if c['state']=='conflict':return hold('explicit_conflict',audit,target)
            if revision==0:
                if c['state']!='known':return hold('unconfirmed_target',audit,target)
                continue
            k=address(memory.policy,root,target,revision,scope,o)
            r=memory.ss.recall(k,domain(target));audit.append({'target':target,'revision':revision,'key':k,'recall':r})
            if r['status']=='memory_disagreement':return hold('memory_disagreement',audit,target)
            if c['state']=='known':
                if r['value'] is not None and r['value']!=c['candidates'][0]:return hold('explicit_value_disagrees',audit,target)
                continue
            if r['value'] is None:return hold(r['status'],audit,target)
            if c['state']=='ambiguous' and r['value'] not in c['candidates']:return hold('outside_current_candidates',audit,target)
            fills.append((target,r['value']))
        current=copy.deepcopy(packet);changes=[]
        for target,value in fills:
            result=apply(model,current,request(current,target,value))
            require(result['status'] in ('updated','unchanged'),'local_completion_failed')
            current=result['packet'];changes.append(result['audit'])
        final=model.recover(current);require(final['status']=='recovered' and not final['pending'],'unresolved_result')
        require(all(final['observation']['cells'][t]==c for t,c in o['cells'].items() if t not in {x[0] for x in fills}),'unrelated_meaning_changed')
        require(digest(packet)==source,'source_modified')
        return {'status':'completed','packet':current,'audit':audit,'changes':changes,'root':root,
                'source_packet_unchanged':True,'eligible_for_inference':False}
    except (ValueError,TypeError,OverflowError) as e:
        return {'status':'abstain','reason':str(e),'eligible_for_inference':False}

def generate(model,memory,scope,packet,order='preserve',goals=None):
    r=complete(model,memory,scope,packet)
    if r['status']!='completed':return r
    g=model.generate(r['packet'],order,goals)
    return {**g,'revision_audit':r['audit'],'changes':r['changes'],'root':r['root']}
