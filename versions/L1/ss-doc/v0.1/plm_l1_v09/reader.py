"""Read clauses with the frozen component; learn the link, keep full-signal contract."""
import json
from .component.algebra import require
from .component.runtime import abstain
from .contract import IDS,normalize,split_document,temporal


def read(model,text):
    try:
        clauses,marker=split_document(text)
        # Public learned marker vocabulary, not a marker->meaning lookup table.
        require(marker in model.meta['training']['marker_inventory'],'unregistered_link_marker')
        events=[]
        for index,clause in enumerate(clauses):
            out=model.component.read(clause)
            require(out['status']=='read','event_read_failed:'+str(index)+':'+out.get('reason','unknown'))
            event=model.component.recover(out['packet'])
            require(event['status']=='recovered','component_signal_unrecoverable')
            events.append(dict(id=IDS[index],**event['meaning']))
        order=list(IDS)
        selected=model.memories['temporal_read'].recall({'marker':marker,'presentation':order})
        require(selected['value'] is not None,'unlearned_temporal_reading')
        time=temporal(json.loads(selected['value']))
        candidate=normalize({'events':events,'presentation':order,'temporal':time},model.codec.candidates)
        packet=model.encode(candidate); recovered=model.recover(packet)
        require(recovered['status']=='recovered','document_signal_unrecoverable')
        require(recovered['meaning']==candidate,'document_signal_mismatch')
        return {'status':'read','packet':packet,'signal_verified':True,'eligible_for_inference':False}
    except (ValueError,TypeError) as error:
        return abstain(str(error))
