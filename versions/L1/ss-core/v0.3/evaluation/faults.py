"""Evaluator-only acquisition impairments. Parameters never enter the guard."""
import hashlib
import numpy as np
from ss_core.clock import ExactPort,PILOT

CONDITIONS=('clean','independent1','independent4','independent16','shared16','pre_shared16','post_noise16','post_truncate','coherent_bias')

class Acquisitions:
    def __init__(self,condition='clean',seed=0,bias_labels=None):
        assert condition in CONDITIONS
        self.condition,self.seed=condition,seed
        self.calls=0
        self.records=[]
        self.bias_labels=bias_labels or {}

    def __call__(self,part,key,nonce):
        call=self.calls;self.calls+=1
        stage='post' if '/post/' in nonce else 'pre'
        shared=self.condition in ('shared16','pre_shared16')
        tag='shared' if shared else str(call)
        number=int.from_bytes(hashlib.sha256((str(self.seed)+'/'+part.seed+'/'+key+'/'+tag).encode()).digest()[:8],'little')
        rng=np.random.default_rng(number)
        sigma={'clean':0,'independent1':1,'independent4':4,'independent16':16,
               'shared16':16,'pre_shared16':16 if stage=='pre' else 0,
               'post_noise16':16 if stage=='post' else 0,'post_truncate':0,'coherent_bias':0}[self.condition]
        h=hashlib.sha256();ticks=0
        for tick,y,mask in ExactPort(part,key,nonce):
            if self.condition=='post_truncate' and stage=='post' and tick>=PILOT+part.dimension+8:break
            if PILOT<=tick<PILOT+part.dimension and sigma:
                y+=sigma*(rng.standard_normal(4)+1j*rng.standard_normal(4))
            if PILOT<=tick<PILOT+part.dimension and self.condition=='coherent_bias':
                index=part.labels.index(tuple(self.bias_labels[key]));j=tick-PILOT
                y+=part.values[:,index,j]*part.context(key)[:,j]
            h.update(y.astype('<c16').tobytes());ticks+=1
            yield tick,y,mask
        self.records.append({'call':call,'stage':stage,'part_seed':part.seed,'key':key,
                             'numeric_waveform_sha256':h.hexdigest(),'emitted_ticks':ticks})
