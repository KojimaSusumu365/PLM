"""One signal: two identity-bound frames, directed time, separate presentation."""
import math
import numpy as np
from .thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MIN_PROOF, MAX_RESIDUAL, LEGACY_MIN_SCORE

from .component.algebra import canonical,require
from .component.banked import FreshBook
from .component.lexicon import ROLES
from .contract import IDS,PRESENTATIONS,TIMES,normalize

MODES=('bound','partitioned','undirected')


class TemporalCodec:
    def __init__(self,candidates,dimension=8192,seed='temporal-development-0',mode='bound'):
        require(type(dimension) is int and 128<=dimension<=16384 and dimension%128==0,'invalid_dimension')
        require(type(seed) is str and 0<len(seed)<=80,'invalid_seed')
        require(type(mode) is str and mode in MODES,'invalid_mode')
        self.candidates={r:tuple(candidates[r]) for r in ROLES}
        self.dimension,self.seed,self.mode=dimension,seed,mode
        self.width=dimension//4 if mode=='partitioned' else dimension
        self.scale=math.sqrt(2.) if mode=='partitioned' else 1/math.sqrt(2.)
        b=FreshBook(self.width,seed)
        self.presence=[]; self.events=[]
        for identity in IDS:
            binding=b.code('event_identity',identity)
            self.presence.append(binding*b.code('event_presence','present'))
            self.events.append({r:np.array([binding*b.code('event_role',r)*b.code('event_value',v) for v in self.candidates[r]]) for r in ROLES})
        self.times=[]
        for time in TIMES:
            code=b.code('temporal_role','edge')*b.code('temporal_kind',time['kind'])
            if time['kind']=='before':
                if mode=='undirected':
                    # Diagnostic: identical endpoints in sorted order erase direction exactly.
                    for identity in IDS:
                        code*=b.code('unordered_endpoint',identity)
                else:
                    code*=b.code('temporal_source',time['source'])*b.code('temporal_target',time['target'])
            self.times.append(code)
        self.times=np.array(self.times)
        self.orders=np.array([b.code('presentation_role','order')*b.code('presentation_value',p) for p in PRESENTATIONS])

    def components(self,meaning):
        m=normalize(meaning,self.candidates)
        parts=[]
        for i,event in enumerate(m['events']):
            frame=self.presence[i].copy()
            for r in ROLES:
                frame+=self.events[i][r][self.candidates[r].index(event[r])]
            parts.append(frame)
        parts.extend([self.times[next(i for i,t in enumerate(TIMES) if t==m['temporal'])],
                      self.orders[PRESENTATIONS.index(m['presentation'])]])
        return parts

    def encode(self,meaning):
        parts=self.components(meaning)
        return (np.concatenate(parts) if self.mode=='partitioned' else sum(parts))*self.scale

    def choose(self,basis,part,reason):
        scores=(basis.conj()@part).real/self.width
        order=np.argsort(-scores,kind='stable')
        top=float(scores[order[0]]); margin=top-max(0.,float(scores[order[1]]))
        require(top>=MIN_SCORE and margin>=MIN_MARGIN,reason)
        return int(order[0]),{'score':round(top,8),'margin':round(margin,8)}

    def recover(self,vector):
        require(isinstance(vector,np.ndarray) and vector.shape==(self.dimension,) and np.isfinite(vector).all(),'invalid_vector')
        raw=vector/self.scale
        parts=[raw[i*self.width:(i+1)*self.width] for i in range(4)] if self.mode=='partitioned' else [raw]*4
        events=[]; audits=[]
        for i in range(2):
            strength=float(np.vdot(self.presence[i],parts[i]).real/self.width)
            require(strength>=MIN_PRESENCE,'event_presence_weak')
            event={'id':IDS[i]}; audit={'id':IDS[i],'presence':round(strength,8),'slots':{}}
            for r in ROLES:
                index,detail=self.choose(self.events[i][r],parts[i],'event_slot_ambiguous')
                event[r]=self.candidates[r][index]; audit['slots'][r]=detail
            events.append(event); audits.append(audit)
        ti,ta=self.choose(self.times,parts[2],'temporal_signal_ambiguous')
        pi,pa=self.choose(self.orders,parts[3],'presentation_signal_ambiguous')
        meaning=normalize({'events':events,'temporal':TIMES[ti],'presentation':PRESENTATIONS[pi]},self.candidates)
        clean=self.encode(meaning)
        residual=float(np.linalg.norm(vector-clean)/np.linalg.norm(clean))
        require(residual<=MAX_RESIDUAL,'document_residual_excessive')
        return {'meaning':meaning,'residual':round(residual,8),'event_audit':audits,'temporal_audit':ta,'presentation_audit':pa}
