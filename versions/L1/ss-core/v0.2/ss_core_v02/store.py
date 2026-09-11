"""SS coefficients plus a value-free pending-scope safety ledger, not answer memory."""
from pathlib import Path
import json
from plm_l1_v09.component.algebra import canonical,digest,require
from ss_revision.memory import RevisionMemory

def scope_id(scope):
    require(type(scope) is dict and set(scope)=={'episode','mutable'},'scope_fields')
    require(type(scope['episode']) is str and 0<len(scope['episode'])<=128,'episode')
    require(type(scope['mutable']) is list and len(scope['mutable'])==2 and
            all(type(t) is str and 0<len(t)<80 for t in scope['mutable']) and len(set(scope['mutable']))==2,'two_targets')
    return digest({'episode':scope['episode'],'mutable':sorted(scope['mutable'])})

class Store:
    def __init__(self,memory,pending=()):
        require(memory.method=='versioned_pair','versioned_pair_only')
        self.memory=memory
        self.pending=set(pending)
        require(all(type(k) is str and len(k)==64 and all(c in '0123456789abcdef' for c in k) for k in self.pending),'pending_hashes')

    @property
    def fingerprint(self):return digest({'memory':self.memory.fingerprint,'pending':sorted(self.pending)})

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False)
        self.memory.save(p/'memory')
        with (p/'pending.json').open('x',encoding='utf-8') as f:
            f.write(canonical({'schema':'ss-core-guard-store-02','pending':sorted(self.pending),'fingerprint':self.fingerprint})+'\n')

    @classmethod
    def load(cls,directory,candidates):
        p=Path(directory);require({x.name for x in p.iterdir()}=={'memory','pending.json'},'store_inventory')
        r=json.loads((p/'pending.json').read_text(encoding='utf-8'))
        require(type(r) is dict and set(r)=={'schema','pending','fingerprint'} and r['schema']=='ss-core-guard-store-02','store_schema')
        require(type(r['pending']) is list and len(r['pending'])==len(set(r['pending'])),'pending_list')
        s=cls(RevisionMemory.load(p/'memory',candidates),r['pending'])
        require(s.fingerprint==r['fingerprint'],'store_fingerprint')
        return s
