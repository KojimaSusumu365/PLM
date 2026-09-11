"""Class-conditional phase centroids and matched exact symbolic feature kernel.

Field-value codes are bundled, multiplied, or bundled up to order three.
Counts, labels, candidate IDs, validation and unanimity remain ordinary control.
"""
import hashlib,itertools,json,math,time
from pathlib import Path
import numpy as np
from .algebra import Book,BatchFeatures,terms,canonical,digest,require

MIN_MARGIN=.02
MAX_CANDIDATES=4
MAX_SELECTION_LOSS=.25
PACKET_SCHEMA='plm-ss-observation-v011'

def rows_checked(rows,fields=None):
    require(type(rows) is list and 0<len(rows)<=4096,'invalid_rows')
    for r in rows:
        require(type(r) is dict and set(r)=={'context','label'},'unexpected_teacher_fields')
        c=r['context'];y=r['label']
        require(type(c) is dict and 1<=len(c)<=6 and all(type(f) is str and 0<len(f)<=64 and type(v) is str and 0<len(v)<=64 for f,v in c.items()),'invalid_context')
        require(type(y) is str and 0<len(y)<=128,'invalid_label')
    fields=sorted(rows[0]['context']) if fields is None else fields
    require(all(sorted(r['context'])==fields for r in rows),'teacher_field_mismatch')
    return fields

def winner(scores,labels):
    order=np.argsort(-np.asarray(scores),kind='stable');top=float(scores[order[0]])
    runner=float(scores[order[1]]) if len(order)>1 else 0.
    margin=round(top-runner,10)
    value=labels[int(order[0])] if top>0 and margin>=MIN_MARGIN else None
    return value,margin

def loss(predictions,rows):
    return sum(.5 if p is None else float(p!=r['label']) for p,r in zip(predictions,rows))/len(rows)

def counts_for(rows,mask,representation,labels):
    out={};class_counts=[sum(r['label']==y for r in rows) for y in labels]
    for r in rows:
        index=labels.index(r['label'])
        for t in terms(mask,representation):
            key=canonical([[f,r['context'][f]] for f in t])
            out.setdefault(key,[0]*len(labels))[index]+=1
    return out,class_counts

def exact_scores(contexts,mask,representation,counts,class_counts):
    ts=terms(mask,representation);out=np.zeros((len(contexts),len(class_counts)))
    for i,c in enumerate(contexts):
        for t in ts:
            if all(f in c for f in t):out[i]+=np.array(counts.get(canonical([[f,c[f]] for f in t]),[0]*len(class_counts)))/class_counts
    return out/len(ts)

class Model:
    def __init__(self,config,members,training,threshold=0.,calibration=None):
        self.config=config;self.members=members;self.training=training;self.threshold=threshold;self.calibration=calibration
        self.books=[Book(m['dimension'],config['seed']) for m in members]
        self.refresh()
    def refresh(self):
        self.meta={'schema':'plm-memory-v011','config':self.config,'training':self.training,'threshold':self.threshold,'calibration':self.calibration,
                   'members':[{k:v for k,v in m.items() if k!='weights'} for m in self.members],'eligible_for_inference':False}
        self.fingerprint=digest([self.meta,[hashlib.sha256(m['weights'].astype('<c16').tobytes()).hexdigest() for m in self.members]])
    def validate_context(self,c):
        require(type(c) is dict and set(c)<=set(self.config['fields']),'unknown_context_fields')
        require(all(type(v) is str and v in self.config['vocabulary'][f] for f,v in c.items()),'unknown_field_value')
    def encode(self,c):
        require(self.config['backend']=='ss','numeric_packet_requires_ss_backend');self.validate_context(c)
        members=[]
        for i,(m,b) in enumerate(zip(self.members,self.books)):
            vector,active=b.vector(c,m['mask'],self.config['representation'])
            members.append({'id':i,'real':vector.real.tolist(),'imag':vector.imag.tolist(),'observed':[True]*m['dimension'],'available_terms':active})
        return {'schema':PACKET_SCHEMA,'model_fingerprint':self.fingerprint,'members':members,'eligible_for_inference':False}
    def _decision(self,scores,active,threshold=None):
        answers=[];labels=self.config['labels']
        for i,(row,n) in enumerate(zip(scores,active)):
            value,margin=winner(row,labels)
            answers.append({'id':i,'value':value if n else None,'margin':margin,'scores':[float(x) for x in row],'available_terms':int(n)})
        values=[a['value'] for a in answers];confidence=min(a['margin'] for a in answers)
        agreed=all(v is not None for v in values) and len(set(values))==1
        gate=self.threshold if threshold is None else threshold
        reason='accepted' if agreed and self.training['supported'] and confidence>=gate else 'unsupported_or_overflow' if not self.training['supported'] else 'candidate_disagreement_or_missing_support' if not agreed else 'empirical_risk_gate'
        return {'value':values[0] if reason=='accepted' else None,'status':'accepted' if reason=='accepted' else 'abstain','reason':reason,
                'confidence':confidence,'members':answers,'eligible_for_inference':False}
    def decode(self,packet,*,threshold=None):
        require(self.config['backend']=='ss','numeric_packet_requires_ss_backend')
        require(type(packet) is dict and set(packet)=={'schema','model_fingerprint','members','eligible_for_inference'},'unexpected_packet_fields')
        require(packet['schema']==PACKET_SCHEMA and packet['model_fingerprint']==self.fingerprint and packet['eligible_for_inference'] is False,'packet_contract_mismatch')
        ps=packet['members'];require(type(ps) is list and len(ps)==len(self.members),'invalid_packet_members')
        scores=[];active=[]
        for i,(p,m) in enumerate(zip(ps,self.members)):
            require(type(p) is dict and set(p)=={'id','real','imag','observed','available_terms'} and type(p['id']) is int and p['id']==i,'invalid_packet_member')
            d=m['dimension'];n=p['available_terms']
            require(type(n) is int and 0<=n<=len(terms(m['mask'],self.config['representation'])),'invalid_term_count')
            require(all(type(p[k]) is list and len(p[k])==d for k in ('real','imag','observed')),'invalid_packet_dimension')
            require(all(type(v) in (int,float) and math.isfinite(v) for k in ('real','imag') for v in p[k]),'invalid_signal_number')
            require(all(type(v) is bool for v in p['observed']),'invalid_observation_mask')
            observed=np.array(p['observed']);q=np.array(p['real'])+1j*np.array(p['imag'])
            require(np.all(q[~observed]==0),'nonzero_erased_coordinate')
            count=int(observed.sum())
            # Mask is side information, not an inferred silence/zero detector.
            score=(m['weights'][:,observed].conj()@q[observed]).real/count if count and n else np.zeros(len(self.config['labels']))
            scores.append(score);active.append(n if count else 0)
        return self._decision(scores,active,threshold)
    def predict(self,c,*,threshold=None):
        self.validate_context(c)
        if self.config['backend']=='ss':return self.decode(self.encode(c),threshold=threshold)
        scores=[];active=[]
        for m in self.members:
            scores.append(exact_scores([c],m['mask'],self.config['representation'],m['counts'],m['class_counts'])[0])
            active.append(sum(all(f in c for f in t) for t in terms(m['mask'],self.config['representation'])))
        return self._decision(scores,active,threshold)
    def storage(self):
        return {'members':len(self.members),'complex_weight_bytes':sum(m['weights'].nbytes for m in self.members),
                'integer_count_entries':sum(sum(len(v) for v in m['counts'].values()) for m in self.members),
                'metadata_utf8_bytes':len(canonical(self.meta).encode('utf-8')),
                'warm_codebook_array_bytes':sum(v.nbytes for b in self.books for v in b.cache.values()),
                'scope':'Owned arrays and serialized metadata, not Python heap, temporaries or process RSS.'}
    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False)
        with (p/'model.json').open('x',encoding='utf-8') as f:f.write(json.dumps({'metadata':self.meta,'fingerprint':self.fingerprint},ensure_ascii=False,indent=2)+'\n')
        np.savez(p/'weights.npz',**{f'member_{i}':m['weights'] for i,m in enumerate(self.members)})
    @classmethod
    def load(cls,directory):
        p=Path(directory);require({f.name for f in p.iterdir()}=={'model.json','weights.npz'},'invalid_model_inventory')
        obj=json.loads((p/'model.json').read_text(encoding='utf-8'));require(set(obj)=={'metadata','fingerprint'},'invalid_model_envelope')
        meta=obj['metadata'];require(meta['schema']=='plm-memory-v011' and meta['eligible_for_inference'] is False,'invalid_model_contract')
        require(1<=len(meta['members'])<=MAX_CANDIDATES,'invalid_member_count')
        members=[]
        with np.load(p/'weights.npz',allow_pickle=False) as arrays:
            require(set(arrays.files)=={f'member_{i}' for i in range(len(meta['members']))},'invalid_weight_inventory')
            for i,m in enumerate(meta['members']):
                w=arrays[f'member_{i}'];shape=(len(meta['config']['labels']),m['dimension']) if meta['config']['backend']=='ss' else (0,0)
                require(w.dtype==np.complex128 and w.shape==shape and np.isfinite(w).all(),'invalid_weights')
                members.append(dict(m,weights=w.copy()))
        model=cls(meta['config'],members,meta['training'],meta['threshold'],meta['calibration'])
        require(model.meta==meta and model.fingerprint==obj['fingerprint'],'model_fingerprint_mismatch')
        return model


def observe(packet,fraction,seed):
    require(type(fraction) in (float,int) and 0<=fraction<=1,'invalid_observation_fraction')
    result=json.loads(json.dumps(packet))
    for p in result['members']:
        d=len(p['real']);rng=np.random.default_rng(int(digest(['v011-mask',seed,d])[:16],16))
        keep=np.zeros(d,dtype=bool);keep[rng.permutation(d)[:int(d*fraction)]]=True
        for i in range(d):
            if not keep[i]:p['real'][i]=p['imag'][i]=0.;p['observed'][i]=False
    return result
