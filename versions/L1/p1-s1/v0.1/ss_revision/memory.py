"""Inference/persistence: ordinary metadata contains revisions but no answer values."""
import json
from pathlib import Path
from plm_l1_v09.component.algebra import canonical,digest,require
from ss_retention.memory import CorrectionMemory
from .context import hexadecimal

METHODS={'none':('none','versioned'),'legacy_context':('split_pair','context'),
         'stable_overwrite':('split_pair','stable'),'versioned_shared':('shared1472','versioned'),
         'versioned_pair':('split_pair','versioned'),'versioned_bank':('split_bank','versioned')}

class RevisionMemory:
    def __init__(self,candidates,method='versioned_pair',seed='revision-code-0'):
        require(method in METHODS,'revision_method')
        self.method,self.seed=method,seed
        inner,self.policy=METHODS[method];self.ss=CorrectionMemory(candidates,inner,seed);self.roots={}

    def register(self,root,targets,protect=True):
        require(hexadecimal(root) and type(protect) is bool,'registration')
        expected={'versions':{t:0 for t in sorted(targets)},'protect':protect}
        require(1<=len(expected['versions'])<=2 and all(type(t) is str and len(t)<80 for t in targets),'registered_targets')
        if root in self.roots:
            require(set(self.roots[root]['versions'])==set(targets) and self.roots[root]['protect']==protect,'scope_policy_changed')
        else:self.roots[root]=expected

    def metadata(self):
        return {'schema':'plm-ss-revision-memory-04','method':self.method,'seed':self.seed,'policy':self.policy,
                'roots':self.roots,'ss_fingerprint':self.ss.fingerprint,'eligible_for_inference':False}

    @property
    def fingerprint(self):return digest(self.metadata())

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False);self.ss.save(p/'ss')
        with (p/'revision.json').open('x',encoding='utf-8') as f:
            f.write(canonical({'metadata':self.metadata(),'fingerprint':self.fingerprint})+'\n')

    @classmethod
    def load(cls,directory,candidates):
        p=Path(directory);require({f.name for f in p.iterdir()}=={'revision.json','ss'},'revision_inventory')
        obj=json.loads((p/'revision.json').read_text(encoding='utf-8'));meta=obj['metadata']
        m=cls(candidates,meta['method'],meta['seed']);m.ss=CorrectionMemory.load(p/'ss',candidates)
        require(m.ss.method==METHODS[m.method][0] and m.ss.seed==m.seed,'inner_memory_contract')
        require(type(meta['roots']) is dict,'roots_contract')
        for root,state in meta['roots'].items():
            require(hexadecimal(root) and type(state) is dict and set(state)=={'versions','protect'},'root_contract')
            require(type(state['versions']) is dict and 1<=len(state['versions'])<=2 and type(state['protect']) is bool,'versions_contract')
            require(all(type(t) is str and len(t)<80 and type(v) is int and 0<=v<=1000000 for t,v in state['versions'].items()),'revision_contract')
        m.roots=meta['roots'];require(m.metadata()==meta and m.fingerprint==obj['fingerprint'],'revision_fingerprint')
        return m

    def cost(self):
        return {**self.ss.cost(),'revision_metadata_bytes':len(canonical(self.metadata()).encode('utf-8')),
                'root_count':len(self.roots),'confirmed_targets':sum(sum(v>0 for v in s['versions'].values()) for s in self.roots.values())}
