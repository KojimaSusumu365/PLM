"""Event binding, superposition and correlation; no text or training corpus."""
import math
import numpy as np
from plm_l1_v06.algebra import require
from plm_l1_v06.banked import FreshBook
from plm_l1_v06.lexicon import ROLES,validate_meaning

MODES=("bound","partitioned","unbound")


class EventCodec:
    def __init__(self,candidates,dimension=8192,seed="events-development-0",mode="bound"):
        require(type(dimension) is int and 128<=dimension<=16384 and dimension%128==0,"invalid_event_dimension")
        require(type(seed) is str and 0<len(seed)<=128,"invalid_event_seed")
        require(type(mode) is str and mode in MODES,"invalid_event_mode")
        self.candidates={r:tuple(candidates[r]) for r in ROLES}
        self.dimension,self.seed,self.mode=dimension,seed,mode
        self.width=dimension//2 if mode=="partitioned" else dimension
        self.scale=1. if mode=="partitioned" else 1/math.sqrt(2.)
        book=FreshBook(self.width,seed)
        presence=book.code("event_presence","present")
        self.bindings=[book.code("event_position",i) if mode=="bound" else np.ones(self.width,dtype=np.complex128) for i in range(2)]
        self.presence=[b*presence for b in self.bindings]
        self.codes=[{r:np.array([b*book.code("event_role",r)*book.code("event_value",v) for v in self.candidates[r]]) for r in ROLES} for b in self.bindings]

    def validate(self,meaning):
        require(type(meaning) is dict and set(meaning)=={"events"},"invalid_two_event_fields")
        require(type(meaning["events"]) is list and len(meaning["events"])==2,"exactly_two_events_required")
        for event in meaning["events"]:
            validate_meaning(event,self.candidates)

    def encode(self,meaning):
        self.validate(meaning)
        frames=[]
        for i,event in enumerate(meaning["events"]):
            frame=self.presence[i].copy()
            for role in ROLES:
                frame+=self.codes[i][role][self.candidates[role].index(event[role])]
            frames.append(frame)
        return np.concatenate(frames) if self.mode=="partitioned" else (frames[0]+frames[1])*self.scale

    def recover(self,vector):
        require(isinstance(vector,np.ndarray) and vector.shape==(self.dimension,) and np.isfinite(vector).all(),"invalid_event_vector")
        meaning={"events":[]}
        audits=[]
        for i in range(2):
            part=vector[i*self.width:(i+1)*self.width] if self.mode=="partitioned" else vector/self.scale
            presence=float(np.vdot(self.presence[i],part).real/self.width)
            require(presence>=.65,"event_presence_weak")
            event,audit={}, {"event_index":i,"presence":round(presence,8),"slots":{}}
            for role in ROLES:
                scores=(self.codes[i][role].conj()@part).real/self.width
                order=np.argsort(-scores,kind="stable")
                top=float(scores[order[0]])
                runner=max(0.,float(scores[order[1]]))
                require(top>=.65 and top-runner>=.25,"event_slot_ambiguous")
                event[role]=self.candidates[role][order[0]]
                audit["slots"][role]={"score":round(top,8),"margin":round(top-runner,8)}
            meaning["events"].append(event)
            audits.append(audit)
        clean=self.encode(meaning)
        residual=float(np.linalg.norm(vector-clean)/np.linalg.norm(clean))
        require(residual<=.20,"event_signal_residual_excessive")
        return {"meaning":meaning,"residual":round(residual,8),"audit":audits}
