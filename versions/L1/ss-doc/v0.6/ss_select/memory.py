"""A small SS scalar-value memory; inference does not import training."""
import hashlib,json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import canonical,digest,require
from plm_l1_v09.component.banked import FreshBook
from .features import NAMES,validate

class SelectorMemory:
    def __init__(self,dimension=256,seed='selector-ss-06'):
        require(type(dimension) is int and 16<=dimension<=4096 and type(seed) is str and 0<len(seed)<96,'selector_shape')
        self.dimension,self.seed=dimension,seed;self.updates=0
        self.basis=np.array([[FreshBook(dimension,seed+'/'+str(k)).code('selection-feature',name) for name in NAMES] for k in range(4)])
        self.weights=np.zeros((4,dimension),complex)

    def encode(self,features):
        validate(features);x=np.array([features[n] for n in NAMES])
        return np.einsum('f,kfd->kd',x,self.basis,optimize=False)/np.sqrt(len(NAMES))

    def predict(self,features):
        x=self.encode(features)
        return float(np.mean(np.einsum('kd,kd->k',x.conj(),self.weights,optimize=False).real/self.dimension))

    def metadata(self):
        return {'schema':'plm-ss-selector-06','dimension':self.dimension,'channels':4,'seed':self.seed,'features':list(NAMES),
                'updates':self.updates,'weights_sha256':hashlib.sha256(self.weights.astype('<c16').tobytes()).hexdigest(),
                'eligible_for_inference':False}

    @property
    def fingerprint(self):return digest(self.metadata())

    def cost(self):return {'coefficient_bytes':self.weights.nbytes,'feature_basis_bytes':self.basis.nbytes,'updates':self.updates}

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False);np.savez_compressed(p/'weights.npz',weights=self.weights)
        with (p/'selector.json').open('x',encoding='utf-8') as f:f.write(canonical({'metadata':self.metadata(),'fingerprint':self.fingerprint})+'\n')

    @classmethod
    def load(cls,directory):
        p=Path(directory);require({x.name for x in p.iterdir()}=={'selector.json','weights.npz'},'selector_inventory')
        obj=json.loads((p/'selector.json').read_text(encoding='utf-8'));meta=obj['metadata'];m=cls(meta['dimension'],meta['seed'])
        with np.load(p/'weights.npz',allow_pickle=False) as z:
            require(set(z.files)=={'weights'},'selector_weight_inventory');w=z['weights']
            require(w.dtype==np.complex128 and w.shape==m.weights.shape and np.isfinite(w).all(),'selector_weights');m.weights=w.copy()
        m.updates=meta['updates'];require(type(m.updates) is int and m.updates>=0,'selector_updates')
        require(m.metadata()==meta and m.fingerprint==obj['fingerprint'],'selector_fingerprint');return m
