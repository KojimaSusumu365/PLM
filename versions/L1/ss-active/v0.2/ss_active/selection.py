"""Teacher-free selection: model plus unlabeled contexts and scalar acquisition ledger."""
import copy
import hashlib
import numpy as np
from ss_multicode.algebra import digest,require
from .base_selection import context_id,normalize_pool,diagnostics

STRATEGIES=('random_once','ambiguity_once','mixed_once','ambiguity_revisit','mixed_revisit')


def validate_config(config):
    require(type(config) is dict and set(config)=={'explore_every','revisit_every','cooldown','drop_margin','max_visits'},'config_schema')
    for k in ('explore_every','revisit_every','cooldown','max_visits'):require(type(config[k]) is int,'integer_config')
    require(config['explore_every'] in (2,4) and config['revisit_every']==4 and config['cooldown']==64 and config['max_visits']==2,'fixed_config_grid')
    require(type(config['drop_margin']) in (float,int) and config['drop_margin'] in (.05,.15),'drop_grid')
    return copy.deepcopy(config)


def normalize_state(state):
    require(type(state) is dict and set(state)=={'schema','pool','ledger','strategy','seed','config','current_step'},'selection_state_schema')
    require(state['schema']=='plm-ss-active2-selection-state','selection_schema')
    s=copy.deepcopy(state);s['pool']=normalize_pool(s['pool']);s['config']=validate_config(s['config'])
    require(s['strategy'] in STRATEGIES and type(s['seed']) is str and 0<len(s['seed'])<=80,'strategy_seed')
    require(type(s['current_step']) is int and s['current_step']>=0 and type(s['ledger']) is dict,'step_ledger')
    ids={r['id'] for r in s['pool']};require(set(s['ledger'])<=ids,'ledger_ids')
    for key,e in s['ledger'].items():
        require(type(e) is dict and set(e)=={'visits','last_step','post_margin'},'label_free_ledger_only')
        require(type(e['visits']) is int and 1<=e['visits']<=2 and type(e['last_step']) is int and 0<e['last_step']<=s['current_step'],'ledger_counts_step')
        require(type(e['post_margin']) in (float,int) and np.isfinite(e['post_margin']) and e['post_margin']>=0,'ledger_margin')
        if s['strategy'].endswith('_once'):require(e['visits']==1,'once_ledger')
    require(sum(e['visits'] for e in s['ledger'].values())<=s['current_step'],'ledger_exceeds_learning_steps')
    return s


def select(model,state):
    require(model.architecture=='concat512','shared_residual_model_required')
    s=normalize_state(state);rows=s['pool'];require(bool(rows),'empty_pool')
    ledger=s['ledger'];cfg=s['config'];index=sum(e['visits'] for e in ledger.values());strategy=s['strategy']
    unseen=[i for i,r in enumerate(rows) if r['id'] not in ledger]
    ties=[digest(['ss-active-order-01',s['seed'],r['id']]) for r in rows]
    scheduled_revisit=strategy.endswith('_revisit') and index%cfg['revisit_every']==cfg['revisit_every']-1
    explore=strategy.startswith('mixed_') and index%cfg['explore_every']==0
    eligible=[]
    if strategy=='random_once' or explore:
        require(bool(unseen),'no_unvisited_candidate')
        chosen=min(unseen,key=lambda i:(ties[i],rows[i]['id']));scored=[rows[chosen]]
        scores=model.raw([rows[chosen]['context']])['readers'];d=diagnostics(scores);score_index=0
        route='random' if strategy=='random_once' else 'explore'
    else:
        scored=rows;scores=model.raw([r['context'] for r in rows])['readers'];d=diagnostics(scores)
        if scheduled_revisit:
            for i,r in enumerate(rows):
                e=ledger.get(r['id'])
                if e and e['visits']<cfg['max_visits'] and s['current_step']-e['last_step']>=cfg['cooldown'] and e['post_margin']-float(d['margin'][i])>=cfg['drop_margin']:
                    eligible.append(i)
        domain=eligible if eligible else unseen
        require(bool(domain),'no_eligible_candidate')
        chosen=min(domain,key=lambda i:(float(d['margin'][i]),ties[i],rows[i]['id']));score_index=chosen
        route='revisit' if eligible else 'ambiguity'
    item=rows[chosen];entry=ledger.get(item['id']);margin=float(d['margin'][score_index])
    result={'schema':'plm-ss-active2-selection','model_fingerprint':model.fingerprint,'state_digest':digest(s),'index':index,
            'selected_id':item['id'],'context':item['context'],'route':route,
            'diagnostics':{'margin':margin,'gini':float(d['gini'][score_index]),'mean_scores':d['mean'][score_index].tolist(),
                'bank_choices':d['bank_choices'][score_index].tolist(),'scheduled_revisit':scheduled_revisit,
                'eligible_revisits':len(eligible),'previous_visits':entry['visits'] if entry else 0,
                'age':s['current_step']-entry['last_step'] if entry else None,
                'margin_drop':entry['post_margin']-margin if entry else None,'contexts_scored_this_call':len(scored),
                'scored_ids_digest':digest([r['id'] for r in scored]),'raw_scores_digest':hashlib.sha256(scores.astype('<f8').tobytes()).hexdigest(),
                'score_is_probability':False},'eligible_for_inference':False}
    result['selection_id']=digest(result);return result
