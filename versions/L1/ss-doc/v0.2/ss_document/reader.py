"""Bounded document reader, using learned lexical and temporal SS memories."""
import itertools
import json
from plm_l1_v09.component.algebra import require
from plm_l1_v09.component.runtime import abstain
from plm_l1_v09.contract import temporal
from .contract import IDS,edge,normalize,split_document


def read(model,text):
    try:
        clauses,markers=split_document(text);events=[]
        require(all(m in model.base.meta['training']['marker_inventory'] for m in markers),'unregistered_link_marker')
        for i,clause in enumerate(clauses):
            out=model.base.component.read(clause);require(out['status']=='read','event_read_failed:'+str(i)+':'+out.get('reason','unknown'))
            recovered=model.base.component.recover(out['packet']);require(recovered['status']=='recovered','component_recovery_failed')
            events.append(dict(id=IDS[i],**recovered['meaning']))
        relations={pair:edge(*pair) for pair in itertools.combinations(IDS[:len(events)],2)}
        for i,marker in enumerate(markers):
            selected=model.base.memories['temporal_read'].recall({'marker':marker,'presentation':list(IDS[:2])})
            require(selected['value'] is not None,'unlearned_link_reading')
            t=temporal(json.loads(selected['value']));rename=dict(zip(IDS[:2],IDS[i:i+2]))
            if t['kind']=='before':relations[IDS[i],IDS[i+1]]=edge(IDS[i],IDS[i+1],rename[t['source']],rename[t['target']])
        candidate=normalize({'events':events,'presentation':list(IDS[:len(events)]),'relations':list(relations.values())},model.codec.candidates)
        packet=model.encode(candidate);out=model.recover(packet)
        require(out['status']=='recovered','document_signal_unrecoverable')
        require(out['meaning']==candidate,'document_signal_mismatch')
        return {'status':'read','packet':packet,'signal_verified':True,'eligible_for_inference':False}
    except (ValueError,TypeError) as e:return abstain(str(e))
