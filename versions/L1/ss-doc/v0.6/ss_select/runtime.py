"""No teacher tables, identifiers as learned features, or learning imports."""
import copy
from plm_l1_v09.component.algebra import digest,require
from ss_revision.context import scope_key,address
from ss_retention.context import domain
from ss_reconfirm.runtime import prompt
from .features import extract

POLICIES=('rule','random','ss_learned')

class Workset:
    def __init__(self,model,entries):
        require(type(entries) is list and 1<=len(entries)<=64,'workset_size');self.entries=copy.deepcopy(entries);self.observations={};ids=set();roots=set()
        for e in self.entries:
            require(type(e) is dict and set(e)=={'id','scope','packet'} and type(e['id']) is str and 0<len(e['id'])<=128,'workset_entry')
            require(e['id'] not in ids,'duplicate_query_id');ids.add(e['id']);rec=model.recover(e['packet']);require(rec['status']=='recovered','unreadable_workset_packet')
            o=rec['observation'];root,targets=scope_key(e['scope'],o)
            require(len(targets)==2 and all(o['cells'][t]['state']=='unobserved' for t in targets),'two_unobserved_targets_required')
            require(root not in roots,'duplicate_scope');roots.add(root);self.observations[e['id']]=(root,targets,o)
        self.fingerprint=digest(self.entries)

    def validate(self):require(digest(self.entries)==self.fingerprint,'workset_changed')

def candidates(memory,workset,excluded=()):
    require(memory.method in ('versioned_shared','versioned_pair'),'selection_content_memory_method')
    workset.validate();excluded=set(tuple(x) for x in excluded);result=[];memory_fp=memory.fingerprint
    valid={(e['id'],t) for e in workset.entries for t in e['scope']['mutable']};require(excluded<=valid,'excluded_target')
    for e in workset.entries:
        root,targets,o=workset.observations[e['id']];require(root in memory.roots,'unregistered_scope')
        recalls={}
        for t in targets:
            revision=memory.roots[root]['versions'][t];require(revision>0,'unconfirmed_target')
            recalls[t]=memory.ss.recall(address(memory.policy,root,t,revision,e['scope'],o),domain(t))
        for t in targets:
            if (e['id'],t) in excluded:continue
            other=next(x for x in targets if x!=t);raw=recalls[t];required=raw['value'] is None
            priority=95 if raw['status']=='memory_disagreement' else 70 if required else 0
            q={'schema':'plm-delayed-confirmation-06','workset_sha256':workset.fingerprint,'id':e['id'],'root':root,'target':t,
               'base_revision':memory.roots[root]['versions'][t],'memory_fingerprint':memory_fp,'packet_sha256':digest(e['packet']),
               'prompt':prompt(t),'required_now':required,'reason':raw['status'] if required else 'optional_retention_check'}
            result.append({'question':q,'priority':priority,'features':extract(raw,recalls[other],memory,o['count'])})
    return result

def choose(memory,workset,policy='ss_learned',selector=None,excluded=(),seed='selection-order-06',step=0):
    require(policy in POLICIES and type(step) is int and step>=0,'selection_policy_step')
    rows=candidates(memory,workset,excluded);require(rows,'no_selection_candidates')
    if policy=='ss_learned':require(selector is not None and selector.updates>0,'trained_selector_required')
    for row in rows:
        q=row['question'];tie=(q['target'],q['id'])
        if policy=='rule':key=(-row['priority'],tie);value=None
        elif policy=='random':key=(digest({'seed':seed,'step':step,'id':q['id'],'target':q['target']}),tie);value=None
        else:value=selector.predict(row['features']);key=(-value,tie)
        row['value_prediction']=value;row['_key']=key
    best=min(rows,key=lambda r:r['_key'])
    return {'status':'selected','policy':policy,**{k:v for k,v in best.items() if k!='_key'},'candidates_scored':len(rows),
            'selector_fingerprint':selector.fingerprint if policy=='ss_learned' else None,'eligible_for_inference':False}
