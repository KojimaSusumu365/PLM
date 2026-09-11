"""Build bounded whole pipelines; omitted joint candidates veto confirmation."""
import math
from .selection import select_candidates
from .base.component.features import observations
from .base.component.training import fit as fit_component
from .base.component.runtime import Model as ComponentModel
from .base.component.banked import fit_banked
from .base.component.algebra import canonical,digest,require
from .base.component.lexicon import validate_lexicon,aligned_examples,ROLES
from .base.contract import normalize,split_document,write_context
from .base.runtime import TemporalModel
from .base.thresholds import values as threshold_values
from .runtime import CommitteeModel

def fit(component_pairs,selection_pairs,temporal_pairs,lexicon,*,method='ss_multi',selection_dimension=2048,selection_seed='candidate-development-0',dimension=8192,seed='temporal-evaluation-0',selection_enabled=True):
    require(method in ('ss_multi','symbolic_multi','ss_single','v09_single'),'invalid_method')
    require(type(selection_seed) is str and 0<len(selection_seed)<=64,'invalid_selection_seed')
    validate_lexicon(lexicon)
    rows=observations(component_pairs,lexicon); validation=observations(selection_pairs,lexicon)
    pools={}; audits={}; components=[]; joint_count=1; joint_complete=True; assignments=[]
    if method=='v09_single':
        components=[fit_component(component_pairs,lexicon,seed='banked-evaluation-0',selector='ss',selection_dimension=selection_dimension,selection_seed='selection-evaluation-0')]
    else:
        for name,values in rows.items():
            pools[name],audits[name]=select_candidates(values,validation[name],method='symbolic' if method=='symbolic_multi' else 'ss',
                                                     dimension=selection_dimension,seed=selection_seed+'/'+name,enabled=selection_enabled)
        names=sorted(pools); joint_count=math.prod(len(pools[n]) for n in names)
        count=1 if method=='ss_single' else min(4,joint_count)
        joint_complete=method=='ss_single' or joint_count<=4
        for i in range(count):
            # Evenly spaced mixed-radix indices cover contrasting module masks
            # without instantiating a potentially large Cartesian product.
            index=0 if count==1 else i*(joint_count-1)//(count-1)
            assignment={}
            for name in reversed(names):
                assignment[name]=index%len(pools[name]); index//=len(pools[name])
            assignments.append(assignment)
            memories={}; stats={}
            for name,values in rows.items():
                selected=pools[name][assignment[name]]
                memories[name],stats[name]=fit_banked(values,8192,'banked-evaluation-0',selected_leaves=selected)
                stats[name].pop('owned_heap_bytes')
            meta={'schema':'plm-l1-component-v09','memory_mode':'split_proof','read_acceptance':'recover_equals_candidate_v1',
                  'seed':'banked-evaluation-0','dimension':8192,'partial':True,'learning':True,'pair_count':len(component_pairs),
                  'pairs_digest':digest(sorted(component_pairs,key=canonical)),'lexicon_digest':digest(lexicon),
                  'kinds':{t['surface']:t['kind'] for t in lexicon['tokens']},'slot_candidates':lexicon['slot_candidates'],
                  'statistics':stats,'supervision_fields':['text','meaning'],'supplied_trace_supervision':False,
                  'dependency_selection':method,'selector_dimension':selection_dimension,'selector_seed':selection_seed,
                  'selector_enabled':selection_enabled,'thresholds':threshold_values(),'eligible_for_inference':False,
                  'candidate_id':f'hypothesis:{i}','selection_validation_count':len(selection_pairs),
                  'selection_validation_digest':digest(sorted(selection_pairs,key=canonical))}
            components.append(ComponentModel(meta,memories))
    require(type(temporal_pairs) is list and 0<len(temporal_pairs)<=10000,'invalid_temporal_pairs')
    temporal_rows={'temporal_read':[],'temporal_write':[]}; markers=set()
    for pair in temporal_pairs:
        require(type(pair) is dict and set(pair)=={'text','meaning'},'only_text_and_meaning_allowed')
        meaning=normalize(pair['meaning'],lexicon['slot_candidates']); clauses,marker=split_document(pair['text'])
        inventory={e['id']:e for e in meaning['events']}
        for clause,identity in zip(clauses,meaning['presentation']):
            aligned_examples([{'text':clause,'meaning':{r:inventory[identity][r] for r in ROLES}}],lexicon)
        markers.add(marker)
        temporal_rows['temporal_read'].append(({'marker':marker,'presentation':meaning['presentation']},canonical(meaning['temporal'])))
        temporal_rows['temporal_write'].append((write_context(meaning['temporal'],meaning['presentation']),canonical(marker)))
    members=[]
    for component in components:
        memories={}; stats={}
        for name,values in temporal_rows.items():
            memories[name],stats[name]=fit_banked(values,8192,seed+'/'+name,partial=False)
            stats[name].pop('owned_heap_bytes')
        train={'pair_count':len(temporal_pairs),'pairs_digest':digest(sorted(temporal_pairs,key=canonical)),'marker_inventory':sorted(markers),
               'learning':True,'statistics':stats,'supervision':['text','meaning'],'supplied_operation_traces':False,
               'memory_dimension':8192,'seed':seed,'dependency_selection':'full designed time contexts; not new temporal feature learning'}
        members.append(TemporalModel(component,memories,train,dimension=dimension,seed=seed))
    meta={'method':method,'supported':joint_complete and all(a['supported'] for a in audits.values()),'member_count':len(members),
          'component_pairs':len(component_pairs),'selection_pairs':len(selection_pairs) if method!='v09_single' else 0,'temporal_pairs':len(temporal_pairs),
          'selection_seed':selection_seed,'selection_dimension':selection_dimension,'selection_enabled':selection_enabled,
          'candidate_assignment':'mixed-radix joint candidates; sample at most four for diagnostics; omitted joint candidates veto multi-model confirmation',
          'joint_plausible_count':joint_count,'joint_candidate_space_complete':joint_complete,
          'single_candidate_ablation':method=='ss_single','member_assignments':assignments,
          'selected_masks':{n:a['selected_masks'] for n,a in audits.items()},'module_support':{n:a['supported'] for n,a in audits.items()},
          'no_online_learning':True}
    model=CommitteeModel(members,meta); model.selection_audit=audits
    return model
