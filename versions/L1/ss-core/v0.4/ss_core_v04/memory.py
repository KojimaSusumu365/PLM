"""Two superposed waveforms, not an array of decoded semantic slot values."""
from dataclasses import dataclass
import hashlib,json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import require
from plm_l1_v09.thresholds import MIN_SCORE,MIN_MARGIN,MAX_RESIDUAL
from .signal import winner

@dataclass
class Cell:
    candidates: np.ndarray
    state: np.ndarray
    arity: np.ndarray
    state_number: int
    count: int
    @property
    def total(self):return self.candidates.sum(axis=0)
    @property
    def ready(self):return self.state_number==0 and self.count==1

class WorkingMemory:
    __slots__=('signal','schema','engine')
    def __init__(self,signal,schema,engine):
        require(isinstance(signal,np.ndarray) and signal.shape==(2,schema.width) and np.isfinite(signal).all(),'wm_signal')
        self.signal,self.schema,self.engine=signal.copy(),schema,engine
    @property
    def fingerprint(self):return hashlib.sha256(self.signal.astype('<c16').tobytes()).hexdigest()

    @classmethod
    def from_document(cls,packet,schema,engine):
        # Numeric packet import only. No semantic recover(), dict or role lookup.
        require(type(packet) is dict and set(packet)=={'schema','model_fingerprint','dimension','real','imag','eligible_for_inference'},'packet_fields')
        require(packet['schema']=='plm-ss-document-signal-01' and packet['model_fingerprint']==schema.source_fingerprint,'packet_model')
        require(type(packet['dimension']) is int and packet['dimension']==schema.width and packet['eligible_for_inference'] is False,'packet_contract')
        for key in ('real','imag'):
            require(type(packet[key]) is list and len(packet[key])==schema.width and all(type(v) in (int,float) for v in packet[key]),'packet_numbers')
        raw=np.asarray(packet['real'],float)+1j*np.asarray(packet['imag'],float)
        require(np.isfinite(raw).all() and np.max(abs(raw))<=32,'packet_finite')
        return cls(np.array([raw*np.sqrt(3.),schema.known_status]),schema,engine)

    def probe(self,address):
        schema=self.schema
        # Public address cleanup validates the operand; it never indexes a value table.
        address_scores=self.engine.correlate(address,schema.addresses,'address04')[0]
        address=schema.addresses[winner(address_scores)].copy()
        allrefs=np.concatenate([schema.values,schema.states,schema.arities])
        refs=np.broadcast_to(allrefs,(2,*allrefs.shape))
        scores=self.engine.correlate(self.signal,refs,'working04',np.broadcast_to(address.conj(),self.signal.shape))
        nv,ns=len(schema.values),len(schema.states)
        si=winner(scores[1,nv:nv+ns]);count=winner(scores[1,nv+ns:])
        require((si==0 and count==1) or (si==1 and count==2) or (si in (2,3) and count==0) or (si==4 and count>=2),'state_arity_mismatch')
        s=scores[0,:nv];rank=np.argsort(-s,kind='stable')
        outside=max([0.]+[float(s[i]) for i in rank[count:]])
        if count:
            inside=float(s[rank[count-1]])
            require(inside>=MIN_SCORE and inside-outside>=MIN_MARGIN,'uncertain_candidates')
        require(outside<=1-MIN_SCORE,'extra_candidate_evidence')
        selected=schema.values[rank[:count]].copy()
        if count:
            evidence=self.engine.correlate(schema.allowed,selected,'domain04',address)[0]
            require(np.all(evidence>=MIN_SCORE),'value_outside_address_domain')
        return Cell(selected,schema.states[si].copy(),schema.arities[count].copy(),si,count)

    def value(self,address):
        c=self.probe(address)
        require(c.ready,'unresolved_working_meaning')
        return c.candidates[0].copy()

    def validate(self,require_complete=False):
        # Reconstruct only waveforms for a residual check, never a semantic record.
        clean=np.array([self.schema.header.copy(),np.zeros(self.schema.width,complex)])
        complete=True
        for address in self.schema.addresses:
            c=self.probe(address)
            clean[0]+=address*c.total
            clean[1]+=address*(c.state+c.arity)
            complete=complete and c.ready
        residual=np.linalg.norm(self.signal-clean,axis=1)/np.maximum(np.linalg.norm(clean,axis=1),1e-12)
        require(np.all(residual<=MAX_RESIDUAL),'working_residual')
        require(not require_complete or complete,'unresolved_working_meaning')
        return {'complete':bool(complete),'residual':residual.tolist()}

    def update(self,address,teacher_signal):
        before=self.fingerprint
        try:
            self.validate()
            address=self.schema.addresses[winner(self.engine.correlate(address,self.schema.addresses,'update_address04')[0])].copy()
            new=self.schema.values[winner(self.engine.correlate(teacher_signal,self.schema.values,'teacher04')[0])].copy()
            old=self.probe(address)
            evidence=self.engine.correlate(self.schema.allowed,new[None,:],'update_domain04',address)[0,0]
            require(evidence>=MIN_SCORE,'teacher_outside_domain')
            candidate=self.signal.copy()
            d0=address*(new-old.total)
            d1=address*(self.schema.states[0]+self.schema.arities[1]-old.state-old.arity)
            for tick in range(self.schema.width):
                candidate[0,tick]+=d0[tick]
                candidate[1,tick]+=d1[tick]
            staged=WorkingMemory(candidate,self.schema,self.engine)
            staged.validate()
            require(np.array_equal(staged.value(address),new),'teacher_not_retained')
            # Scan all other addresses, not merely a single anchor.
            for other in self.schema.addresses:
                if np.array_equal(other,address):continue
                a,b=self.probe(other),staged.probe(other)
                require(a.state_number==b.state_number and a.count==b.count and np.allclose(a.total,b.total,atol=1e-10,rtol=0),'non_target_changed')
            return staged,{'status':'updated','before':before,'after':staged.fingerprint,'write_ticks':self.schema.width,'non_target_fields_checked':len(self.schema.addresses)-1}
        except ValueError as e:
            return self,{'status':'held','reason':str(e),'before':before,'after':self.fingerprint}

    def save(self,path):
        path=Path(path);path.mkdir(parents=True,exist_ok=False)
        np.savez_compressed(path/'signal.npz',signal=self.signal)
        with (path/'state.json').open('x',encoding='utf-8') as f:
            json.dump({'schema':'ss-working04','schema_fingerprint':self.schema.fingerprint,'signal_sha256':self.fingerprint},f,sort_keys=True)

    @classmethod
    def load(cls,path,schema,engine):
        path=Path(path)
        require({p.name for p in path.iterdir()}=={'state.json','signal.npz'},'wm_inventory')
        m=json.loads((path/'state.json').read_text(encoding='utf-8'))
        require(set(m)=={'schema','schema_fingerprint','signal_sha256'} and m['schema']=='ss-working04' and m['schema_fingerprint']==schema.fingerprint,'wm_schema')
        with np.load(path/'signal.npz',allow_pickle=False) as a:
            require(a.files==['signal'],'wm_arrays');obj=cls(a['signal'],schema,engine)
        require(obj.fingerprint==m['signal_sha256'],'wm_hash')
        return obj
