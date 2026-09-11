"""Numerical two-event contract and atomic generation. No reader/learner imports."""
import json
from pathlib import Path
import numpy as np
from plm_l1_v06.algebra import canonical,digest,require
from plm_l1_v06.runtime import Model as ComponentModel,abstain
from plm_l1_v06.lexicon import GOALS
from .codec import EventCodec

PACKET_FIELDS={"schema","model_fingerprint","dimension","real","imag","eligible_for_inference"}


class EventModel:
    def __init__(self,component,*,dimension=8192,seed="events-development-0",mode="bound"):
        require(isinstance(component,ComponentModel),"invalid_component_model")
        self.component=component
        self.codec=EventCodec(component.meta["slot_candidates"],dimension,seed,mode)
        self.meta={"schema":"plm-two-event-model-v1","component_fingerprint":component.fingerprint,
                   "dimension":dimension,"seed":seed,"mode":mode,"event_count":2,
                   "event_positions":"mention_order_only","terminator":"。","binding_learning":"designed_not_learned",
                   "read_acceptance":"recover_equals_both_candidates_v1","eligible_for_inference":False}
        self.fingerprint=digest(self.meta)

    def encode(self,meaning):
        v=self.codec.encode(meaning)
        return {"schema":"plm-two-event-signal-v1","model_fingerprint":self.fingerprint,"dimension":self.codec.dimension,
                "real":v.real.tolist(),"imag":v.imag.tolist(),"eligible_for_inference":False}

    def recover(self,packet):
        try:
            require(type(packet) is dict and set(packet)==PACKET_FIELDS,"unexpected_packet_fields")
            require(packet["schema"]=="plm-two-event-signal-v1" and packet["model_fingerprint"]==self.fingerprint,"packet_model_mismatch")
            require(type(packet["dimension"]) is int and packet["dimension"]==self.codec.dimension and packet["eligible_for_inference"] is False,"invalid_packet_contract")
            for field in ("real","imag"):
                require(type(packet[field]) is list and len(packet[field])==self.codec.dimension and all(type(v) in (int,float) for v in packet[field]),"invalid_signal_values")
            vector=np.array(packet["real"],dtype=float)+1j*np.array(packet["imag"],dtype=float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector))<=32.,"invalid_signal_values")
            return {"status":"recovered",**self.codec.recover(vector),"eligible_for_inference":False}
        except (ValueError,TypeError,OverflowError) as error:
            return abstain(str(error),meaning=None)

    def read(self,text):
        from .reader import read
        return read(self,text)

    def generate(self,packet,goals=("subject","subject")):
        try:
            require(type(goals) in (list,tuple) and len(goals)==2 and all(type(g) is str and g in GOALS for g in goals),"invalid_event_goals")
            recovered=self.recover(packet)
            require(recovered["status"]=="recovered",recovered.get("reason","event_recovery_failed"))
            texts=[]
            for index,event in enumerate(recovered["meaning"]["events"]):
                out=self.component.generate(self.component.encode(event),goals[index])
                require(out["status"]=="generated","event_generation_failed:"+str(index)+":"+out.get("reason","unknown"))
                texts.append(out["text"])
            return {"status":"generated","text":"".join(texts),"event_count":2,"eligible_for_inference":False}
        except (ValueError,TypeError) as error:
            return abstain(str(error))

    def save(self,directory):
        target=Path(directory)
        require(not (target/"model.json").exists() and not (target/"component").exists(),"output_exists")
        target.mkdir(parents=True,exist_ok=True)
        self.component.save(target/"component")
        with (target/"model.json").open("x",encoding="utf-8") as stream:
            stream.write(json.dumps({"metadata":self.meta,"fingerprint":self.fingerprint},ensure_ascii=False,indent=2)+"\n")

    @classmethod
    def load(cls,directory):
        target=Path(directory)
        info=json.loads((target/"model.json").read_text(encoding="utf-8"))
        require(type(info) is dict and set(info)=={"metadata","fingerprint"},"invalid_model_envelope")
        m=info["metadata"]
        model=cls(ComponentModel.load(target/"component"),dimension=m["dimension"],seed=m["seed"],mode=m["mode"])
        require(model.meta==m and model.fingerprint==info["fingerprint"],"model_hash_mismatch")
        return model
