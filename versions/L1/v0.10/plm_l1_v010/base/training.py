"""Learn temporal text/graph correspondences from pairs, no supplied operation traces."""
from .component.algebra import canonical,digest,require
from .component.lexicon import aligned_examples,ROLES,validate_lexicon
from .component.training import fit as fit_component
from .component.banked import fit_banked
from .contract import normalize,split_document,write_context
from .runtime import TemporalModel


def fit(component_pairs,temporal_pairs,lexicon,*,seed='temporal-development-0',dimension=8192,mode='bound',learning=True,selector='ss',selection_dimension=2048,selection_seed='selection-development-0',selection_enabled=True):
    validate_lexicon(lexicon)
    require(type(temporal_pairs) is list and 0<len(temporal_pairs)<=10000,'invalid_temporal_pairs')
    require(type(learning) is bool and type(seed) is str and 0<len(seed)<=80,'invalid_training_settings')
    rows={'temporal_read':[],'temporal_write':[]}; markers=set()
    for pair in temporal_pairs:
        require(type(pair) is dict and set(pair)=={'text','meaning'},'only_text_and_meaning_allowed')
        m=normalize(pair['meaning'],lexicon['slot_candidates'])
        clauses,marker=split_document(pair['text'])
        inventory={e['id']:e for e in m['events']}
        # Lexical/slot alignment, not the learned reader or an evaluator oracle.
        for clause,identity in zip(clauses,m['presentation']):
            aligned_examples([{'text':clause,'meaning':{r:inventory[identity][r] for r in ROLES}}],lexicon)
        markers.add(marker)
        rows['temporal_read'].append(({'marker':marker,'presentation':m['presentation']},canonical(m['temporal'])))
        rows['temporal_write'].append((write_context(m['temporal'],m['presentation']),canonical(marker)))
    memories={}; statistics={}
    for name,observations in rows.items():
        memories[name],statistics[name]=fit_banked(observations,8192,seed+'/'+name,partial=False,enabled=learning,mode='split_proof')
        statistics[name].pop('owned_heap_bytes')
    component=fit_component(component_pairs,lexicon,seed='banked-evaluation-0',dimension=8192,selector=selector,selection_dimension=selection_dimension,selection_seed=selection_seed,selection_enabled=selection_enabled)
    training={'pair_count':len(temporal_pairs),'pairs_digest':digest(sorted(temporal_pairs,key=canonical)),
              'marker_inventory':sorted(markers),'learning':learning,'statistics':statistics,
              'supervision':['text','meaning'],'supplied_operation_traces':False,
              'memory_dimension':8192,'seed':seed,'dependency_selection':'full designed relation-context keys; no temporal feature selection'}
    return TemporalModel(component,memories,training,dimension=dimension,seed=seed,mode=mode)
