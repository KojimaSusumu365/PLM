"""Explicit two-sentence boundary; event structure is designed, not learned."""
from plm_l1_v06.algebra import require
from plm_l1_v06.runtime import abstain


def read(model,text):
    try:
        require(type(text) is str and 0<len(text)<=514,"invalid_document_text")
        parts=text.strip().split(model.meta["terminator"])
        require(len(parts)==3 and parts[-1]=="" and all(p.strip() for p in parts[:2]),"exactly_two_terminated_sentences_required")
        events=[]
        for index,part in enumerate(parts[:2]):
            out=model.component.read(part.strip()+model.meta["terminator"])
            require(out["status"]=="read","event_read_failed:"+str(index)+":"+out.get("reason","unknown"))
            recovered=model.component.recover(out["packet"])
            require(recovered["status"]=="recovered","component_signal_unrecoverable")
            events.append(recovered["meaning"])
        candidate={"events":events}
        packet=model.encode(candidate)
        recovered=model.recover(packet)
        require(recovered["status"]=="recovered","two_event_signal_unrecoverable")
        require(recovered["meaning"]==candidate,"two_event_signal_mismatch")
        return {"status":"read","packet":packet,"event_count":2,"signal_verified":True,"eligible_for_inference":False}
    except (ValueError,TypeError) as error:
        return abstain(str(error))
