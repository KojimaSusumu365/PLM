"""Prediction-only model. Tentative guesses are never teacher feedback."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book,canonical,digest,require


def decisions(scores,labels):
    x=np.asarray(scores,dtype=float)
    require(x.ndim==2 and x.shape[1]==len(labels) and np.isfinite(x).all(),'invalid_scores')
    output=[]
    for row in x:
        order=np.argsort(-row,kind='stable')
        margin=float(row[order[0]]-row[order[1]])
        hits=[y for y,s in zip(labels,row) if s>=.5]
        output.append({'tentative':labels[order[0]] if margin>1e-12 else None,
                       'accepted':hits[0] if len(hits)==1 else None,
                       'reason':'accepted' if len(hits)==1 else 'no_support' if not hits else 'conflicting_support',
                       'margin':margin,'scores':[float(v) for v in row],
                       'score_is_probability':False,'eligible_for_inference':False})
    return output


class Model:
    def __init__(self,config,weights=None,entries=None):
        self.config=copy.deepcopy(config)
        c=self.config
        require(set(c)=={'backend','dimension','seed','fields','vocabulary','labels'},'model_config_schema')
        require(c['backend'] in ('ss','exact') and type(c['seed']) is str and 0<len(c['seed'])<=80,'invalid_backend_seed')
        require(type(c['dimension']) is int and (8<=c['dimension']<=4096 if c['backend']=='ss' else c['dimension']==0),'invalid_dimension')
        require(type(c['fields']) is list and 1<=len(c['fields'])<=6 and all(type(f) is str for f in c['fields']) and c['fields']==sorted(set(c['fields'])),'invalid_fields')
        require(set(c['vocabulary'])==set(c['fields']) and all(type(v) is list and 1<=len(v)<=16 and all(type(s) is str for s in v) and v==sorted(set(v)) for v in c['vocabulary'].values()),'invalid_vocabulary')
        require(type(c['labels']) is list and 2<=len(c['labels'])<=16 and all(type(y) is str for y in c['labels']) and c['labels']==sorted(set(c['labels'])),'invalid_labels')
        shape=(len(c['labels']),c['dimension']) if c['backend']=='ss' else (0,0)
        self.weights=np.zeros(shape,dtype=np.complex128) if weights is None else np.array(weights,copy=True)
        require(self.weights.shape==shape and self.weights.dtype==np.complex128 and np.isfinite(self.weights).all(),'invalid_weights')
        self.entries=copy.deepcopy(entries or {})
        require(type(self.entries) is dict and (c['backend']!='ss' or not self.entries),'ss_cannot_save_key_table')
        require(all(y in c['labels'] for y in self.entries.values()),'invalid_exact_label')
        for k in self.entries:self.validate(json.loads(k))
        self.book=Book(c['dimension'],'online-01/'+c['seed'])
        self.refresh()

    def validate(self,context):
        require(type(context) is dict and sorted(context)==self.config['fields'],'complete_context_required')
        require(all(type(v) is str and v in self.config['vocabulary'][f] for f,v in context.items()),'unknown_field_value')

    def vector(self,context):
        self.validate(context)
        return self.book.vector(context,self.config['fields'],'product')[0]

    def score_vector(self,vector):
        return (self.weights.conj()@vector).real/self.config['dimension']

    def scores(self,contexts):
        for c in contexts:self.validate(c)
        if not contexts:return np.empty((0,len(self.config['labels'])))
        if self.config['backend']=='ss':
            b=np.array([self.vector(c) for c in contexts])
            return (b@self.weights.conj().T).real/self.config['dimension']
        return np.array([[int(y==self.entries.get(canonical(c))) for y in self.config['labels']] for c in contexts],dtype=float)

    def predict(self,contexts):return decisions(self.scores(contexts),self.config['labels'])

    def refresh(self):
        require(np.isfinite(self.weights).all(),'nonfinite_update')
        self.metadata={'schema':'plm-ss-online-model-01','config':self.config,'entries':self.entries,'threshold':.5,'eligible_for_inference':False}
        self.fingerprint=digest([self.metadata,hashlib.sha256(self.weights.astype('<c16').tobytes()).hexdigest()])

    def storage(self):
        return {'weight_bytes':int(self.weights.nbytes),'metadata_utf8_bytes':len(canonical(self.metadata).encode('utf-8')),
                'warm_atom_bytes':sum(v.nbytes for v in self.book.cache.values()),'exact_entries':len(self.entries),
                'weight_energy':float(np.sum(np.abs(self.weights)**2)),
                'scope':'Owned arrays and JSON payloads, not total RSS/energy/hardware precision.'}

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False)
        with (p/'model.json').open('x',encoding='utf-8') as f:json.dump({'metadata':self.metadata,'fingerprint':self.fingerprint},f,ensure_ascii=False,indent=2)
        np.savez(p/'weights.npz',weights=self.weights)

    @classmethod
    def load(cls,directory):
        p=Path(directory);require({x.name for x in p.iterdir()}=={'model.json','weights.npz'},'model_inventory')
        obj=json.loads((p/'model.json').read_text(encoding='utf-8'));m=obj['metadata']
        require(m['schema']=='plm-ss-online-model-01' and m['threshold']==.5 and m['eligible_for_inference'] is False,'model_contract')
        with np.load(p/'weights.npz',allow_pickle=False) as z:
            require(z.files==['weights'],'weight_inventory')
            model=cls(m['config'],z['weights'],m['entries'])
        require(model.metadata==m and model.fingerprint==obj['fingerprint'],'model_fingerprint_mismatch')
        return model
