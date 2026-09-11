"""Compare whole candidate meanings/texts. Never splice candidate slots or strings."""
import json
from pathlib import Path
from .base.component.algebra import canonical,digest,require
from .base.component.runtime import abstain
from .base.runtime import TemporalModel,PACKET_FIELDS
from .policy import values as policy_values

SCHEMA='plm-l1-committee-model-v010'
PACKET_SCHEMA='plm-l1-committee-signal-v010'

class CommitteeModel:
    def __init__(self,members,training):
        require(type(members) in (list,tuple) and 1<=len(members)<=4 and all(isinstance(m,TemporalModel) for m in members),'invalid_members')
        require(type(training) is dict and type(training.get('supported')) is bool,'invalid_training_metadata')
        self.members=tuple(members); first=self.members[0]
        require(all((m.meta['dimension'],m.meta['seed'],m.meta['mode'],m.codec.candidates)==(first.meta['dimension'],first.meta['seed'],first.meta['mode'],first.codec.candidates) for m in members),'incompatible_candidate_codecs')
        self.meta={'schema':SCHEMA,'member_fingerprints':[m.fingerprint for m in members],
                   'candidate_ids':[f'hypothesis:{i}' for i in range(len(members))],'training':json.loads(canonical(training)),
                   'policy':policy_values(),'decision':'all_complete_candidates_equal_or_abstain','eligible_for_inference':False}
        self.fingerprint=digest(self.meta)

    def encode(self,meaning):
        p=self.members[0].encode(meaning)
        return dict(p,schema=PACKET_SCHEMA,model_fingerprint=self.fingerprint)

    def _member_packet(self,packet,index):
        require(type(packet) is dict and set(packet)==PACKET_FIELDS,'unexpected_packet_fields')
        require(packet['schema']==PACKET_SCHEMA and packet['model_fingerprint']==self.fingerprint,'packet_model_mismatch')
        return dict(packet,schema='plm-temporal-signal-v09',model_fingerprint=self.members[index].fingerprint)

    def recover(self,packet):
        try: return self.members[0].recover(self._member_packet(packet,0))
        except (ValueError,TypeError,KeyError) as e: return abstain(str(e),meaning=None)

    def read(self,text):
        from .reader import read
        return read(self,text)

    def generate(self,packet,goals=('subject','subject'),order='preserve'):
        try:
            recovered=self.recover(packet); require(recovered['status']=='recovered',recovered.get('reason','unrecoverable_signal'))
            outputs=[m.generate(self._member_packet(packet,i),goals,order) for i,m in enumerate(self.members)]
            audits=[{'id':self.meta['candidate_ids'][i],'status':out['status'],'text':out.get('text'),'reason':out.get('reason')} for i,out in enumerate(outputs)]
            if not all(o['status']=='generated' for o in outputs): return abstain('candidate_generation_unsupported',candidate_audit=audits)
            if len({o['text'] for o in outputs})!=1: return abstain('candidate_generation_disagreement',candidate_audit=audits)
            if not self.meta['training']['supported']:
                return abstain('unsupported_or_incomplete_candidate_family',candidate_audit=audits)
            return dict(outputs[0],candidate_audit=audits,decision='complete_text_unanimity')
        except (ValueError,TypeError,KeyError) as e: return abstain(str(e))

    def save(self,directory):
        target=Path(directory); require(not target.exists() or not any(target.iterdir()),'fresh_model_directory_required')
        target.mkdir(parents=True,exist_ok=True)
        for i,m in enumerate(self.members): m.save(target/f'member-{i}')
        with (target/'model.json').open('x',encoding='utf-8') as f:
            f.write(json.dumps({'metadata':self.meta,'fingerprint':self.fingerprint},ensure_ascii=False,indent=2)+'\n')

    @classmethod
    def load(cls,directory):
        target=Path(directory); info=json.loads((target/'model.json').read_text(encoding='utf-8'))
        require(type(info) is dict and set(info)=={'metadata','fingerprint'},'invalid_model_envelope')
        meta=info['metadata']; require(meta.get('schema')==SCHEMA and 1<=len(meta['member_fingerprints'])<=4,'invalid_model_metadata')
        expected={'model.json'}|{f'member-{i}' for i in range(len(meta['member_fingerprints']))}
        require({p.name for p in target.iterdir()}==expected,'invalid_member_inventory')
        model=cls([TemporalModel.load(target/f'member-{i}') for i in range(len(meta['member_fingerprints']))],meta['training'])
        require(model.meta==meta and model.fingerprint==info['fingerprint'],'model_hash_mismatch')
        return model
