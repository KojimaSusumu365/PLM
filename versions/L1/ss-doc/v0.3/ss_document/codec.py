"""Count, occurrence-bound slots, pair-bound time and presentation in one SS vector."""
import itertools
import math
import numpy as np
from plm_l1_v09.component.banked import FreshBook
from plm_l1_v09.component.lexicon import ROLES
from plm_l1_v09.component.algebra import require
from plm_l1_v09.thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MAX_RESIDUAL
from .contract import IDS,edge,normalize

MODES=('bound','unbound_events','undirected_time')


class DocumentCodec:
    def __init__(self,candidates,dimension=8192,seed='ssdoc-code-0',mode='bound'):
        require(type(dimension) is int and 128<=dimension<=16384 and dimension%128==0,'dimension')
        require(type(seed) is str and 0<len(seed)<=80 and mode in MODES,'seed_mode')
        self.dimension=dimension;self.seed=seed;self.mode=mode
        self.candidates={r:tuple(candidates[r]) for r in ROLES};b=FreshBook(dimension,'ssdoc-v01/'+seed)
        self.counts=np.array([b.code('count',n) for n in (2,3)])
        self.presence=[];self.events=[]
        for identity in IDS:
            identity_code=b.code('occurrence',identity)
            self.presence.append(identity_code*b.code('presence',True))
            binding=np.ones(dimension,complex) if mode=='unbound_events' else identity_code
            self.events.append({r:np.array([binding*b.code('role',r)*b.code('value',v) for v in self.candidates[r]]) for r in ROLES})
        self.pairs=list(itertools.combinations(IDS,2));self.relations={};self.relation_values={}
        for a,c in self.pairs:
            values=[edge(a,c),edge(a,c,a,c),edge(a,c,c,a)];self.relation_values[a,c]=values
            basis=[]
            for e in values:
                v=b.code('time_pair',[a,c])*b.code('time_kind',e['kind'])
                if e['kind']=='before':
                    if mode=='undirected_time':v*=b.code('unordered_endpoints',[a,c])
                    else:v*=b.code('source',e['source'])*b.code('target',e['target'])
                basis.append(v)
            self.relations[a,c]=np.array(basis)
        self.orders={n:list(map(list,itertools.permutations(IDS[:n]))) for n in (2,3)}
        self.order_codes={n:np.array([b.code('presentation',p) for p in self.orders[n]]) for n in (2,3)}

    def encode(self,meaning):
        m=normalize(meaning,self.candidates);n=len(m['events']);v=self.counts[n-2].copy()
        for i,e in enumerate(m['events']):
            v+=self.presence[i]
            for role in ROLES:v+=self.events[i][role][self.candidates[role].index(e[role])]
        for r in m['relations']:
            pair=tuple(r['pair']);v+=self.relations[pair][self.relation_values[pair].index(r)]
        v+=self.order_codes[n][self.orders[n].index(m['presentation'])]
        return v/math.sqrt(3.)

    def choose(self,basis,raw,reason):
        scores=(basis.conj()@raw).real/self.dimension;order=np.argsort(-scores,kind='stable')
        top=float(scores[order[0]]);gap=top-max(0.,float(scores[order[1]]))
        require(top>=MIN_SCORE and gap>=MIN_MARGIN,reason)
        return int(order[0]),{'score':round(top,8),'margin':round(gap,8)}

    def recover(self,vector):
        require(isinstance(vector,np.ndarray) and vector.shape==(self.dimension,) and np.isfinite(vector).all(),'finite_document_vector')
        raw=vector*math.sqrt(3.);ci,ca=self.choose(self.counts,raw,'ambiguous_event_count');n=ci+2
        events=[];audits=[]
        for i in range(n):
            strength=float(np.vdot(self.presence[i],raw).real/self.dimension)
            require(strength>=MIN_PRESENCE,'missing_event_presence');e={'id':IDS[i]};a={'id':IDS[i],'presence':round(strength,8),'slots':{}}
            for role in ROLES:
                j,detail=self.choose(self.events[i][role],raw,'ambiguous_event_slot');e[role]=self.candidates[role][j];a['slots'][role]=detail
            events.append(e);audits.append(a)
        relations=[];ra=[]
        for pair in itertools.combinations(IDS[:n],2):
            j,a=self.choose(self.relations[pair],raw,'ambiguous_time_direction');relations.append(self.relation_values[pair][j]);ra.append(a)
        j,oa=self.choose(self.order_codes[n],raw,'ambiguous_presentation')
        m=normalize({'events':events,'relations':relations,'presentation':self.orders[n][j]},self.candidates)
        clean=self.encode(m);residual=float(np.linalg.norm(vector-clean)/np.linalg.norm(clean))
        require(residual<=MAX_RESIDUAL,'document_residual_excessive')
        return {'meaning':m,'residual':round(residual,8),'count_audit':ca,'event_audit':audits,'relation_audit':ra,'order_audit':oa}

    def storage(self):
        arrays=[self.counts,*self.presence,*self.relations.values(),*self.order_codes.values()]
        arrays += [a for e in self.events for a in e.values()]
        return {'document_basis_bytes':sum(a.nbytes for a in arrays),'complex_signal_bytes':16*self.dimension,
                'designed_bases_not_learned_weights':True}
