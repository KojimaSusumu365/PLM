"""Generator imports neither reader nor teacher/oracle; only learned base and SS packet."""
import json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import canonical,digest,require
from plm_l1_v09.component.lexicon import ROLES,GOALS
from plm_l1_v09.component.runtime import abstain
from plm_l1_v09.runtime import TemporalModel
from plm_l1_v09.contract import write_context
from plm_l1_v09.thresholds import values
from .codec import DocumentCodec
from .contract import IDS,pair_relation,local_time

PACKET_FIELDS={'schema','model_fingerprint','dimension','real','imag','eligible_for_inference'}


class DocumentModel:
    def __init__(self,base,dimension=8192,seed='ssdoc-code-0',mode='bound',condition='normal'):
        require(isinstance(base,TemporalModel),'learned_temporal_base_required')
        require(condition in ('normal','zero_temporal_read','zero_temporal_write','zero_lexical_write'),'condition')
        self.base=base;self.codec=DocumentCodec(base.component.meta['slot_candidates'],dimension,seed,mode)
        self.meta={'schema':'plm-ss-document-model-01','base_fingerprint':base.fingerprint,'dimension':dimension,'seed':seed,
                   'mode':mode,'condition':condition,'thresholds':values(),
                   'capacity':'two_or_three_local_occurrences','relations':'explicit_adjacent_before_or_unknown_no_transitive_inference',
                   'structure':'designed_count_identity_pair_bindings_and_punctuation','eligible_for_inference':False}
        self.fingerprint=digest(self.meta)

    def packet(self,vector):
        require(isinstance(vector,np.ndarray) and vector.shape==(self.codec.dimension,) and np.isfinite(vector).all(),'vector_shape')
        return {'schema':'plm-ss-document-signal-01','model_fingerprint':self.fingerprint,'dimension':self.codec.dimension,
                'real':vector.real.tolist(),'imag':vector.imag.tolist(),'eligible_for_inference':False}

    def encode(self,meaning):return self.packet(self.codec.encode(meaning))

    def recover(self,packet):
        try:
            require(type(packet) is dict and set(packet)==PACKET_FIELDS,'unexpected_packet_fields')
            require(packet['schema']=='plm-ss-document-signal-01' and packet['model_fingerprint']==self.fingerprint,'packet_model_mismatch')
            require(type(packet['dimension']) is int and packet['dimension']==self.codec.dimension and packet['eligible_for_inference'] is False,'packet_contract')
            for name in ('real','imag'):
                require(type(packet[name]) is list and len(packet[name])==self.codec.dimension and all(type(v) in (int,float) for v in packet[name]),'numeric_signal_only')
            vector=np.asarray(packet['real'],float).astype(complex);vector.imag=np.asarray(packet['imag'],float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector))<=32,'finite_bounded_signal')
            return {'status':'recovered',**self.codec.recover(vector),'eligible_for_inference':False}
        except (ValueError,TypeError,OverflowError) as e:return abstain(str(e),meaning=None)

    def read(self,text):
        from .reader import read
        return read(self,text)

    def generate(self,packet,order='preserve',goals=None):
        try:
            require(type(order) is str and order in ('preserve','reverse'),'order_goal')
            rec=self.recover(packet);require(rec['status']=='recovered',rec.get('reason','recovery_failed'));m=rec['meaning'];n=len(m['events'])
            if goals is None:goals=['subject']*n
            require(type(goals) in (tuple,list) and len(goals)==n and all(type(g) is str and g in GOALS for g in goals),'per_event_goals')
            ids=m['presentation'] if order=='preserve' else list(reversed(m['presentation']))
            inventory={e['id']:e for e in m['events']};texts=[];audits=[]
            for i,identity in enumerate(ids):
                e={r:inventory[identity][r] for r in ROLES}
                out=self.base.component.generate(self.base.component.encode(e),goals[i])
                require(out['status']=='generated','event_generation_failed:'+str(i)+':'+out.get('reason','unknown'))
                marker=''
                if i:
                    r=pair_relation(m,ids[i-1],identity);rename=dict(zip(r['pair'],IDS[:2]))
                    context=write_context(local_time(r),[rename[ids[i-1]],rename[identity]])
                    selected=self.base.memories['temporal_write'].recall(context)
                    require(selected['value'] is not None,'unlearned_link_generation')
                    marker=json.loads(selected['value'])
                    require(type(marker) is str and marker in self.base.meta['training']['marker_inventory'],'learned_marker_inventory')
                    audits.append({'positions':[i-1,i],'selection':selected})
                texts.append(marker+out['text'])
            return {'status':'generated','text':''.join(texts),'event_order':list(ids),'link_audit':audits,'eligible_for_inference':False}
        except (ValueError,TypeError) as e:return abstain(str(e))

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False);self.base.save(p/'base')
        (p/'document.json').write_text(canonical({'metadata':self.meta,'fingerprint':self.fingerprint})+'\n',encoding='utf-8')

    @classmethod
    def load(cls,directory):
        p=Path(directory);require({x.name for x in p.iterdir()}=={'base','document.json'},'model_inventory')
        obj=json.loads((p/'document.json').read_text(encoding='utf-8'));m=obj['metadata']
        model=cls(TemporalModel.load(p/'base'),m['dimension'],m['seed'],m['mode'],m['condition'])
        require(model.meta==m and model.fingerprint==obj['fingerprint'],'model_fingerprint')
        return model
