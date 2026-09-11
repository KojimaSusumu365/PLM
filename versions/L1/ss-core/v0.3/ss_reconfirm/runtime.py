"""Read-only SS assessment and generation. No teacher or learning imports."""
import copy
from plm_l1_v09.component.algebra import require
from ss_partial.update import apply,request
from ss_retention.context import domain
from ss_revision.context import address

POLICIES=('legacy','always','ss_selective')

def prompt(target):
    if target.startswith('time/'):
        a,b=target[5:].split(',');return f'事象{int(a.split(":")[1])+1}と事象{int(b.split(":")[1])+1}の時間関係を確認してください。'
    event,role=target.split('/');name={'subject':'主体','object':'対象','predicate':'行為','polarity':'肯否','modality':'仮定の有無'}[role]
    return f'事象{int(event.split(":")[1])+1}の{name}を確認してください。'

def assess(model,memory,session,policy='ss_selective'):
    try:
        require(policy in POLICIES,'confirmation_policy');o,targets=session.validate(model,memory)
        decisions=[];questions=[];versions=memory.roots[session.root]['versions']
        for target in targets:
            c=o['cells'][target];revision=versions[target];reason=None;priority=0;raw=None;value=None;source=None
            if target in session.confirmed:source='external_confirmation_this_session'
            else:
                k=address(memory.policy,session.root,target,revision,session.scope,o)
                raw=memory.ss.recall(k,domain(target)) if revision else {'status':'unconfirmed','value':None,'raw':{}}
                value=raw['value']
                if policy=='always':reason,priority='always_confirm',10
                elif c['state']=='conflict':reason,priority='explicit_conflict',100
                elif raw['status']=='memory_disagreement':reason,priority='memory_disagreement',95
                elif c['state']=='known':
                    if value is not None and value!=c['candidates'][0]:reason,priority='explicit_value_disagrees',90
                    elif policy=='ss_selective' and value is None:reason,priority='unverified_explicit_value',80
                    else:source='ss_supported_observation' if value is not None else 'legacy_explicit_fallback'
                elif value is None:reason,priority=raw['status'],70
                elif c['state']=='ambiguous' and value not in c['candidates']:reason,priority='outside_current_candidates',90
                else:source='ss_memory'
            decision={'target':target,'revision':revision,'state':c['state'],'source':source,'reason':reason,'recall':raw}
            decisions.append(decision)
            if reason is not None:
                q={'schema':'plm-confirmation-question-05','root':session.root,'target':target,'base_revision':revision,
                   'packet_sha256':session.bound_packet,'memory_fingerprint':session.bound_memory,'reason':reason,
                   'priority':priority,'prompt':prompt(target)}
                questions.append(q)
        questions.sort(key=lambda q:(-q['priority'],q['target']))
        return {'status':'needs_confirmation' if questions else 'ready','policy':policy,'questions':questions,'decisions':decisions,
                'eligible_for_inference':False}
    except (ValueError,TypeError,OverflowError) as e:return {'status':'abstain','reason':str(e),'eligible_for_inference':False}

def complete(model,memory,session,policy='ss_selective'):
    plan=assess(model,memory,session,policy)
    if plan['status']!='ready':return plan
    try:
        original,_=session.validate(model,memory);current=copy.deepcopy(session.packet);changes=[]
        for d in plan['decisions']:
            if d['source']=='ss_memory':
                r=apply(model,current,request(current,d['target'],d['recall']['value']))
                require(r['status'] in ('updated','unchanged'),'ss_completion_failed');current=r['packet'];changes.append(r['audit'])
        rec=model.recover(current);require(rec['status']=='recovered' and not rec['pending'],'incomplete_result')
        filled={c['target'] for c in changes}
        require(all(rec['observation']['cells'][t]==v for t,v in original['cells'].items() if t not in filled),'unrelated_cell_changed')
        return {'status':'completed','packet':current,'decisions':plan['decisions'],'changes':changes,'policy':policy,'eligible_for_inference':False}
    except (ValueError,TypeError,OverflowError) as e:return {'status':'abstain','reason':str(e),'eligible_for_inference':False}

def generate(model,memory,session,policy='ss_selective',order='preserve',goals=None):
    r=complete(model,memory,session,policy)
    if r['status']!='completed':return r
    return {**model.generate(r['packet'],order,goals),'confirmation_policy':policy,'decisions':r['decisions'],'changes':r['changes']}
