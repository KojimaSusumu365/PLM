"""Temporal packet and generation. No reader, trainer or language oracle required."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .component.algebra import canonical,digest,require
from .component.runtime import Model as ComponentModel,abstain
from .component.banked import BankedMemory,MemoryBlock
from .component.lexicon import ROLES,GOALS
from .codec import TemporalCodec
from .contract import normalize,write_context
from .thresholds import values as threshold_values

PACKET_FIELDS={'schema','model_fingerprint','dimension','real','imag','eligible_for_inference'}
MEMORIES=('temporal_read','temporal_write')


class TemporalModel:
    def __init__(self,component,memories,training,*,dimension=8192,seed='temporal-development-0',mode='bound'):
        require(isinstance(component,ComponentModel) and type(memories) is dict and set(memories)==set(MEMORIES),'invalid_model_parts')
        self.codec=TemporalCodec(component.meta['slot_candidates'],dimension,seed,mode)
        require(type(training) is dict and training['seed']==seed and training['memory_dimension']==8192,'invalid_training_metadata')
        markers=training['marker_inventory']
        require(type(markers) is list and bool(markers) and all(type(x) is str for x in markers),'invalid_marker_inventory')
        require(markers==sorted(set(markers)) and all(x=='' or 1<len(x)<=25 and x.endswith('、') and x.count('、')==1 and '。' not in x for x in markers),'invalid_marker_inventory')
        for name,memory in memories.items():
            require(isinstance(memory,BankedMemory),'invalid_memory')
            for block in memory.blocks:
                meta=block.meta()
                require(meta['seed']==seed+'/'+name and meta['budget']==8192 and meta['mode']==3,'memory_contract_mismatch')
        self.component,self.memories=component,memories
        self.meta={'schema':'plm-temporal-model-v09','component_fingerprint':component.fingerprint,
                   'dimension':dimension,'seed':seed,'mode':mode,'training':json.loads(canonical(training)),
                   'event_identity':'local_occurrence_id_stable_within_packet_not_cross_document',
                   'presentation':'separate_from_identity_and_temporal_edge','relation':'explicit_before_or_unknown_only',
                   'binding_and_boundaries':'designed_not_learned','read_acceptance':'recover_equals_own_full_candidate',
                   'thresholds':threshold_values(),
                   'eligible_for_inference':False}
        self.fingerprint=digest({'metadata':self.meta,'weights':{n:[hashlib.sha256(b.blob).hexdigest() for b in memories[n].blocks] for n in MEMORIES}})

    def encode(self,meaning):
        vector=self.codec.encode(meaning)
        return {'schema':'plm-temporal-signal-v09','model_fingerprint':self.fingerprint,'dimension':self.codec.dimension,
                'real':vector.real.tolist(),'imag':vector.imag.tolist(),'eligible_for_inference':False}

    def recover(self,packet):
        try:
            require(type(packet) is dict and set(packet)==PACKET_FIELDS,'unexpected_packet_fields')
            require(packet['schema']=='plm-temporal-signal-v09' and packet['model_fingerprint']==self.fingerprint,'packet_model_mismatch')
            require(type(packet['dimension']) is int and packet['dimension']==self.codec.dimension and packet['eligible_for_inference'] is False,'invalid_packet_contract')
            for field in ('real','imag'):
                require(type(packet[field]) is list and len(packet[field])==self.codec.dimension and all(type(v) in (int,float) for v in packet[field]),'invalid_signal_values')
            real=np.array(packet['real'],dtype=float); imag=np.array(packet['imag'],dtype=float)
            require(np.isfinite(real).all() and np.isfinite(imag).all(),'invalid_signal_values')
            vector=real.astype(np.complex128); vector.imag=imag
            require(np.max(np.abs(vector))<=32.,'invalid_signal_values')
            return {'status':'recovered',**self.codec.recover(vector),'eligible_for_inference':False}
        except (ValueError,TypeError,OverflowError) as error:
            return abstain(str(error),meaning=None)

    def read(self,text):
        from .reader import read
        return read(self,text)

    def generate(self,packet,goals=('subject','subject'),order='preserve'):
        try:
            require(type(goals) in (list,tuple) and len(goals)==2 and all(type(g) is str and g in GOALS for g in goals),'invalid_goals')
            require(type(order) is str and order in ('preserve','reverse'),'invalid_order_goal')
            recovered=self.recover(packet)
            require(recovered['status']=='recovered',recovered.get('reason','recovery_failed'))
            m=recovered['meaning']; ids=m['presentation'] if order=='preserve' else list(reversed(m['presentation']))
            selected=self.memories['temporal_write'].recall(write_context(m['temporal'],ids))
            require(selected['value'] is not None,'unlearned_temporal_realization')
            marker=json.loads(selected['value'])
            require(type(marker) is str and marker in self.meta['training']['marker_inventory'],'invalid_learned_marker')
            inventory={e['id']:e for e in m['events']}; texts=[]
            for index,identity in enumerate(ids):
                event={r:inventory[identity][r] for r in ROLES}
                out=self.component.generate(self.component.encode(event),goals[index])
                require(out['status']=='generated','event_generation_failed:'+str(index)+':'+out.get('reason','unknown'))
                texts.append(out['text'])
            return {'status':'generated','text':texts[0]+marker+texts[1],'event_order':list(ids),'eligible_for_inference':False}
        except (ValueError,TypeError) as error:
            return abstain(str(error))

    def save(self,directory):
        target=Path(directory)
        require(not target.exists() or not any(target.iterdir()),'fresh_model_directory_required')
        target.mkdir(parents=True,exist_ok=True)
        self.component.save(target/'component')
        weights={}; groups={}
        for name in MEMORIES:
            groups[name]=[]
            for i,block in enumerate(self.memories[name].blocks):
                key=name+'_'+str(i); groups[name].append(key)
                weights[key]=np.frombuffer(block.blob,dtype=np.uint8)
        np.savez_compressed(target/'weights.npz',**weights)
        with (target/'model.json').open('x',encoding='utf-8') as f:
            f.write(json.dumps({'metadata':self.meta,'fingerprint':self.fingerprint,'groups':groups},ensure_ascii=False,indent=2)+'\n')

    @classmethod
    def load(cls,directory):
        target=Path(directory)
        info=json.loads((target/'model.json').read_text(encoding='utf-8'))
        require(type(info) is dict and set(info)=={'metadata','fingerprint','groups'},'invalid_model_envelope')
        m=info['metadata']; groups=info['groups']
        require(type(groups) is dict and set(groups)==set(MEMORIES),'invalid_memory_inventory')
        require(all(type(keys) is list and bool(keys) and all(type(k) is str for k in keys) for keys in groups.values()),'invalid_weight_groups')
        keys=[k for group in groups.values() for k in group]
        require(len(keys)==len(set(keys)),'duplicate_weight_key')
        with np.load(target/'weights.npz',allow_pickle=False) as weights:
            require(set(keys)==set(weights.files) and all(weights[k].dtype==np.uint8 and weights[k].ndim==1 for k in keys),'invalid_weights')
            memories={n:BankedMemory([MemoryBlock(weights[k].tobytes()) for k in groups[n]]) for n in MEMORIES}
        model=cls(ComponentModel.load(target/'component'),memories,m['training'],dimension=m['dimension'],seed=m['seed'],mode=m['mode'])
        require(model.meta==m and model.fingerprint==info['fingerprint'],'model_hash_mismatch')
        return model
