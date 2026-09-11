"""Inference and persistence only. Learned answers live exclusively in SS coefficients."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import canonical,digest,require
from plm_l1_v09.component.banked import FreshBook
from .context import labels

METHODS=('none','shared736','shared1472','split_pair','split_bank')
POLICY={'score':0.5,'margin':0.15,'minimum_channel_votes':3,'channels':4,'learning_gain':1.0}

class ChannelMemory:
    def __init__(self,kind,dimension,seed,label_inventory):
        require(kind in ('pair','bank') and type(dimension) is int and dimension>=16,'memory_shape')
        self.kind,self.dimension,self.seed=kind,dimension,seed
        self.labels=tuple(tuple(x) for x in label_inventory);self.books=[FreshBook(dimension,seed+'/'+str(i)) for i in range(4)]
        self.values=np.array([[b.code('label',list(x)) for x in self.labels] for b in self.books]) if kind=='pair' else None
        self.weights=np.zeros((4,dimension) if kind=='pair' else (4,len(self.labels),dimension),complex)
        self.registry=set();self.updates=0;self.cache=OrderedDict()

    def context(self,k):
        require(type(k) is str and len(k)==64 and all(c in '0123456789abcdef' for c in k),'context_digest')
        if k in self.cache:
            self.cache.move_to_end(k);return self.cache[k]
        value=np.array([b.code('context',k) for b in self.books]);self.cache[k]=value
        if len(self.cache)>32:self.cache.popitem(last=False)
        return value

    def scores(self,k):
        c=self.context(k)
        if self.kind=='pair':
            return np.einsum('kld,kd->kl',self.values.conj(),self.weights*c.conj(),optimize=False).real/self.dimension
        return np.einsum('kld,kd->kl',self.weights,c.conj(),optimize=False).real/self.dimension

    def recall(self,k,role):
        all_scores=self.scores(k);indexes=[i for i,x in enumerate(self.labels) if x[0]==role]
        require(len(indexes)>=2,'query_domain')
        s=all_scores[:,indexes];means=s.mean(axis=0);order=np.argsort(-means,kind='stable');best=int(order[0])
        top=float(means[best]);gap=top-max(0.,float(means[order[1]]));votes=int(np.sum(np.argmax(s,axis=1)==best))
        accepted=top>=POLICY['score'] and int(np.sum(means>=POLICY['score']))==1 and gap>=POLICY['margin'] and votes>=POLICY['minimum_channel_votes']
        return {'value':self.labels[indexes[best]][1] if accepted else None,'top_value':self.labels[indexes[best]][1],
                'scores':[[round(float(v),8) for v in row] for row in s],
                'mean_scores':[round(float(v),8) for v in means],'score':round(top,8),'margin':round(gap,8),
                'votes':votes,'registered':k in self.registry,'accepted_raw':bool(accepted)}

    def cost(self):
        return {'coefficient_bytes':self.weights.nbytes,'label_basis_bytes':0 if self.values is None else self.values.nbytes,
                'context_cache_bytes':sum(v.nbytes for v in self.cache.values()),
                'registry_json_bytes':len(canonical(sorted(self.registry)).encode('utf-8')),'registered_keys':len(self.registry),'updates':self.updates}

class CorrectionMemory:
    def __init__(self,candidates,method='split_pair',seed='retention-code-0'):
        require(method in METHODS and type(seed) is str and 0<len(seed)<96,'method_seed')
        self.labels=labels(candidates);require(len(self.labels)==23,'fixed_23_label_inventory')
        self.method,self.seed=method,seed;self.parts={}
        if method!='none':self.parts['main']=ChannelMemory('pair',1472 if method=='shared1472' else 736,seed+'/main',self.labels)
        if method=='split_pair':self.parts['protected']=ChannelMemory('pair',736,seed+'/protected',self.labels)
        if method=='split_bank':self.parts['protected']=ChannelMemory('bank',32,seed+'/protected',self.labels)

    def recall(self,k,role):
        raw={name:m.recall(k,role) for name,m in self.parts.items()}
        if not raw:return {'status':'no_memory','value':None,'raw':raw}
        registered=[name for name,m in self.parts.items() if k in m.registry]
        if not registered:return {'status':'unregistered','value':None,'raw':raw}
        selected='protected' if 'protected' in registered else 'main'
        r=raw[selected]
        if r['value'] is None:return {'status':'weak_support','value':None,'raw':raw}
        if selected=='protected' and raw['main']['value'] is not None and raw['main']['value']!=r['value']:
            return {'status':'memory_disagreement','value':None,'raw':raw}
        return {'status':'supported','value':r['value'],'selected':selected,'raw':raw}

    def registered(self,k):return any(k in m.registry for m in self.parts.values())

    def metadata(self):
        return {'schema':'plm-correction-memory-03','method':self.method,'seed':self.seed,'labels':[list(x) for x in self.labels],
                'policy':POLICY,'parts':{name:{'kind':m.kind,'dimension':m.dimension,'seed':m.seed,
                    'registry':sorted(m.registry),'updates':m.updates,'weights_sha256':hashlib.sha256(m.weights.astype('<c16').tobytes()).hexdigest()}
                    for name,m in self.parts.items()},'eligible_for_inference':False}

    @property
    def fingerprint(self):return digest(self.metadata())

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False)
        np.savez_compressed(p/'weights.npz',**{k:m.weights for k,m in self.parts.items()})
        with (p/'state.json').open('x',encoding='utf-8') as f:f.write(canonical({'metadata':self.metadata(),'fingerprint':self.fingerprint})+'\n')

    @classmethod
    def load(cls,directory,candidates):
        p=Path(directory);require({x.name for x in p.iterdir()}=={'state.json','weights.npz'},'memory_file_inventory')
        obj=json.loads((p/'state.json').read_text(encoding='utf-8'));meta=obj['metadata'];m=cls(candidates,meta['method'],meta['seed'])
        with np.load(p/'weights.npz',allow_pickle=False) as z:
            require(set(z.files)==set(m.parts),'weight_inventory')
            for name,part in m.parts.items():
                w=z[name];require(w.dtype==np.complex128 and w.shape==part.weights.shape and np.isfinite(w).all(),'weight_contract')
                part.weights=w.copy();part.registry=set(meta['parts'][name]['registry']);part.updates=meta['parts'][name]['updates']
                require(type(part.updates) is int and part.updates>=0,'update_count')
        require(m.metadata()==meta and m.fingerprint==obj['fingerprint'],'memory_fingerprint')
        return m

    def cost(self):
        c={name:p.cost() for name,p in self.parts.items()}
        return {'parts':c,'total_coefficient_bytes':sum(x['coefficient_bytes'] for x in c.values()),
                'label_basis_bytes':sum(x['label_basis_bytes'] for x in c.values()),'context_cache_bytes':sum(x['context_cache_bytes'] for x in c.values()),
                'metadata_bytes':len(canonical(self.metadata()).encode('utf-8'))}
