"""Short-lived interaction provenance, separate from persistent SS memory."""
import copy,json
from pathlib import Path
from plm_l1_v09.component.algebra import canonical,digest,require
from ss_revision.context import scope_key

class Session:
    def __init__(self,model,memory,scope,packet):
        rec=model.recover(packet);require(rec['status']=='recovered','session_source_unreadable')
        root,_=scope_key(scope,rec['observation']);require(root in memory.roots,'unregistered_scope')
        self.scope=copy.deepcopy(scope);self.packet=copy.deepcopy(packet);self.root=root;self.confirmed={}
        self.bound_memory=memory.fingerprint;self.bound_packet=digest(packet)

    def validate(self,model,memory):
        require(memory.fingerprint==self.bound_memory and digest(self.packet)==self.bound_packet,'stale_session')
        rec=model.recover(self.packet);require(rec['status']=='recovered','session_source_unreadable')
        root,targets=scope_key(self.scope,rec['observation']);require(root==self.root and root in memory.roots,'session_scope')
        require(type(self.confirmed) is dict and set(self.confirmed)<=set(targets),'confirmation_receipts')
        for target,revision in self.confirmed.items():
            require(type(revision) is int and revision==memory.roots[root]['versions'][target] and revision>0,'receipt_revision')
            require(rec['observation']['cells'][target]['state']=='known','receipt_requires_known')
        return rec['observation'],targets

    def payload(self):
        return {'schema':'plm-reconfirmation-session-05','scope':self.scope,'packet':self.packet,'root':self.root,
                'confirmed':self.confirmed,'bound_memory':self.bound_memory,'bound_packet':self.bound_packet,'eligible_for_inference':False}

    def save(self,path):
        payload=self.payload()
        with Path(path).open('x',encoding='utf-8') as f:f.write(canonical({'payload':payload,'fingerprint':digest(payload)})+'\n')

    @classmethod
    def load(cls,path,model,memory):
        obj=json.loads(Path(path).read_text(encoding='utf-8'));require(type(obj) is dict and set(obj)=={'payload','fingerprint'},'session_file')
        p=obj['payload'];require(type(p) is dict and set(p)=={'schema','scope','packet','root','confirmed','bound_memory','bound_packet','eligible_for_inference'},'session_fields')
        require(p['schema']=='plm-reconfirmation-session-05' and p['eligible_for_inference'] is False and digest(p)==obj['fingerprint'],'session_fingerprint')
        s=cls(model,memory,p['scope'],p['packet']);s.confirmed=p['confirmed']
        require(s.bound_memory==p['bound_memory'] and s.bound_packet==p['bound_packet'] and s.root==p['root'],'stale_session')
        s.validate(model,memory);return s
