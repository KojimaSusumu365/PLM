"""Fixed-budget phase memory: projected-key routing and pair evidence.

Each immutable block owns only a padded byte string containing metadata and
complex128 weights. No stored key list, membership set, tree or code cache.
The optional inference cache is a fixed-size bytearray, never serialized.
"""
import hashlib
import json
import struct
import sys
import numpy as np
from ..thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MIN_PROOF, MAX_RESIDUAL, LEGACY_MIN_SCORE

from .algebra import canonical, require
from .projection import structure_code, dependency_leaves

MODES = {"single":0,"split":1,"proof":2,"split_proof":3,"split_unchecked":4}
META_BYTES = 2048
CACHE_SLOTS = 32
CACHE_SLOT_BYTES = 4096


class FreshBook:
    """Same phase generator as algebra.Book, arbitrary internal width, no cache."""
    __slots__ = ("dimension","seed")
    def __init__(self,dimension,seed):
        self.dimension,self.seed=dimension,seed
    def code(self,namespace,value):
        key=canonical(["plm-l1-phase-u53-v1",self.seed,namespace,value])
        raw=hashlib.shake_256(key.encode("utf-8")).digest(8*self.dimension)
        phase=(np.frombuffer(raw,dtype="<u8")>>11).astype(float)*(2.**-53)*(2*np.pi)
        return np.exp(1j*phase)


def key_code(book,fields):
    out=book.code("field_set",sorted(fields))
    for field in sorted(fields):
        out*=structure_code(book,fields[field],"field:"+field)
    return out


def value_code(book,label):
    try:
        value=json.loads(label)
    except (json.JSONDecodeError,TypeError):
        value=label
    return book.code("target_namespace","target")*structure_code(book,value)


def route(key,banks):
    return int.from_bytes(hashlib.sha256(canonical(["plm-routing-v1",key]).encode("utf-8")).digest()[:8],"little")%banks


def bank_count(load,budget,mode):
    if mode not in (1,3,4):
        return 1
    banks=1
    while load>8*banks and banks<8 and budget//(2*banks)>=128:
        banks*=2
    return banks


def bank_seed(seed,index,banks):
    return seed if banks==1 else seed+"/bank:"+str(index)


class MemoryBlock:
    __slots__=("_blob",)
    def __init__(self,blob):
        require(type(blob) is bytes and len(blob)>META_BYTES,"invalid_block")
        n=struct.unpack_from("<I",blob)[0]
        require(0<n<=META_BYTES-4,"invalid_block_header")
        meta=json.loads(blob[4:4+n].decode("utf-8"))
        required={"schema","seed","budget","mode","mask","candidates","banks","counts","value_width","proof_width"}
        require(set(meta)==required and meta["schema"]=="plm-banked-block-v1","invalid_block_metadata")
        require(type(meta["budget"]) is int and 128<=meta["budget"]<=16384 and meta["budget"]%128==0,"invalid_block_budget")
        require(type(meta["mode"]) is int and meta["mode"] in MODES.values(),"invalid_block_mode")
        require(meta["banks"] in (1,2,4,8) and len(meta["counts"])==meta["banks"],"invalid_banks")
        require(all(type(c) is int and c>=0 for c in meta["counts"]) and 0<sum(meta["counts"])<=256,"invalid_load")
        require(meta["value_width"]>0 and meta["proof_width"]>=0 and meta["banks"]*(meta["value_width"]+meta["proof_width"])==meta["budget"],"invalid_layout")
        require(meta["proof_width"]==(meta["budget"]//meta["banks"]//4 if meta["mode"] in (2,3,4) else 0),"invalid_proof_layout")
        require(meta["mask"]==sorted(set(meta["mask"])) and all(type(s) is str for s in meta["mask"]),"invalid_mask")
        require(meta["candidates"]==sorted(set(meta["candidates"])) and bool(meta["candidates"]) and all(type(s) is str for s in meta["candidates"]),"invalid_candidates")
        require(meta["banks"]==bank_count(sum(meta["counts"]),meta["budget"],meta["mode"]),"invalid_bank_policy")
        require(type(meta["seed"]) is str and 0<len(meta["seed"])<=128,"invalid_seed")
        require(len(blob)==META_BYTES+16*meta["budget"] and not any(blob[4+n:META_BYTES]),"invalid_block_size_or_padding")
        require(np.isfinite(np.frombuffer(blob,dtype="<c16",offset=META_BYTES)).all(),"invalid_block_weights")
        self._blob=blob
    @property
    def blob(self):
        return self._blob
    def meta(self):
        n=struct.unpack_from("<I",self.blob)[0]
        return json.loads(self.blob[4:4+n].decode("utf-8"))
    def recall(self,context):
        m=self.meta()
        require(all(f in context for f in m["mask"]),"missing_query_field")
        key={f:context[f] for f in m["mask"]}
        bank=route(key,m["banks"])
        dv,dp=m["value_width"],m["proof_width"]
        weights=np.frombuffer(self.blob,dtype="<c16",offset=META_BYTES)
        start=bank*(dv+dp)
        book=FreshBook(dv,bank_seed(m["seed"],bank,m["banks"]))
        query=weights[start:start+dv]*key_code(book,key)
        scores=np.array([float(np.vdot(value_code(book,c),query).real/dv) for c in m["candidates"]])
        order=np.argsort(-scores,kind="stable")
        top=float(scores[order[0]])
        runner=max(0.,float(scores[order[1]])) if len(order)>1 else 0.
        candidate=m["candidates"][order[0]]
        good=top>=MIN_SCORE and top-runner>=MIN_MARGIN
        evidence=None
        if dp:
            proof=FreshBook(dp,bank_seed(m["seed"],bank,m["banks"])+"/pair-evidence")
            expected=proof.code("key_value_pair",[key,candidate])
            evidence=float(np.vdot(expected,weights[start+dv:start+dv+dp]).real/dp)
            if m["mode"] in (2,3):
                good=good and evidence>=MIN_PROOF
        return {"mask":m["mask"],"bank":bank,"bank_load":m["counts"][bank],"banks":m["banks"],
                "value":candidate if good else None,"score":round(top,8),"margin":round(top-runner,8),
                "evidence":None if evidence is None else round(evidence,8),"evidence_required":m["mode"] in (2,3)}


class BankedMemory:
    __slots__=("blocks","cache")
    def __init__(self,blocks,cache_slots=CACHE_SLOTS):
        require(type(cache_slots) is int and cache_slots in (0,CACHE_SLOTS),"invalid_cache_size")
        self.blocks=tuple(blocks)
        require(bool(self.blocks),"empty_memory")
        self.cache=bytearray(cache_slots*CACHE_SLOT_BYTES)
    def recall(self,context):
        fields=sorted({f for b in self.blocks for f in b.meta()["mask"]})
        require(all(f in context for f in fields),"missing_query_field")
        identity=canonical({f:context[f] for f in fields})
        slot=None
        if self.cache:
            index=int.from_bytes(hashlib.sha256(identity.encode("utf-8")).digest()[:8],"little")%CACHE_SLOTS
            slot=index*CACHE_SLOT_BYTES
            n=struct.unpack_from("<I",self.cache,slot)[0]
            if n:
                cached=json.loads(self.cache[slot+4:slot+4+n])
                if cached[0]==identity:
                    return cached[1]
        audits=[b.recall(context) for b in self.blocks]
        accepted={a["value"] for a in audits if a["value"] is not None}
        result={"value":next(iter(accepted)) if len(accepted)==1 else None,
                "reason":"recalled" if len(accepted)==1 else "weak_unregistered_or_conflicting_projection","projections":audits}
        if slot is not None:
            payload=canonical([identity,result]).encode("utf-8")
            if len(payload)<=CACHE_SLOT_BYTES-4:
                self.cache[slot:slot+CACHE_SLOT_BYTES]=struct.pack("<I",len(payload))+payload+b"\0"*(CACHE_SLOT_BYTES-4-len(payload))
        return result
    def clear_cache(self):
        self.cache[:]=b"\0"*len(self.cache)
    def storage(self):
        return {"state_bytes":sum(len(b.blob) for b in self.blocks),"cache_capacity_bytes":len(self.cache),
                "owned_heap_bytes":sys.getsizeof(self)+sys.getsizeof(self.blocks)+sys.getsizeof(self.cache)+sum(sys.getsizeof(b)+sys.getsizeof(b.blob) for b in self.blocks),
                "numerical_weight_bytes":sum(16*b.meta()["budget"] for b in self.blocks)}


def fit_banked(observations,dimension,seed,*,partial=True,enabled=True,mode="split_proof",cache_slots=CACHE_SLOTS,selected_leaves=None):
    require(type(mode) is str and mode in MODES and type(dimension) is int and 128<=dimension<=16384 and dimension%128==0,"invalid_memory_settings")
    require(type(enabled) is bool and type(seed) is str and 0<len(seed)<=128,"invalid_memory_settings")
    leaves=dependency_leaves(observations,partial) if selected_leaves is None else selected_leaves
    require(bool(leaves) and len({canonical(c) for c,_ in leaves})<=256,"memory_capacity_exceeded")
    masks=sorted({tuple(sorted(c)) for c,_ in leaves})
    blocks=[]
    for mask in masks:
        grouped={}
        for context,label in leaves:
            if tuple(sorted(context))!=mask:
                continue
            identity=canonical(context)
            if identity not in grouped:
                grouped[identity]=[context,{}]
            counts_for_key=grouped[identity][1]
            counts_for_key[label]=counts_for_key.get(label,0)+1
        selected=[grouped[k] for k in sorted(grouped)]
        banks=bank_count(len(selected),dimension,MODES[mode])
        dp=dimension//banks//4 if MODES[mode] in (2,3,4) else 0
        dv=dimension//banks-dp
        vector=np.zeros(dimension,dtype="<c16")
        counts=[0]*banks
        for context,label_counts in selected:
            bank=route(context,banks)
            counts[bank]+=1
            if enabled:
                book=FreshBook(dv,bank_seed(seed,bank,banks))
                start=bank*(dv+dp)
                total=sum(label_counts.values())
                mean=sum(value_code(book,label)*(n/total) for label,n in sorted(label_counts.items()))
                vector[start:start+dv]+=key_code(book,context).conj()*mean
                if dp:
                    proof=FreshBook(dp,bank_seed(seed,bank,banks)+"/pair-evidence")
                    vector[start+dv:start+dv+dp]+=sum(proof.code("key_value_pair",[context,label])*(n/total) for label,n in sorted(label_counts.items()))
        meta={"schema":"plm-banked-block-v1","seed":seed,"budget":dimension,"mode":MODES[mode],"mask":list(mask),
              "candidates":sorted({t for _,counts_for_key in selected for t in counts_for_key}),"banks":banks,"counts":counts,"value_width":dv,"proof_width":dp}
        payload=canonical(meta).encode("utf-8")
        require(len(payload)<=META_BYTES-4,"metadata_capacity_exceeded")
        blob=struct.pack("<I",len(payload))+payload+b"\0"*(META_BYTES-4-len(payload))+vector.tobytes()
        blocks.append(MemoryBlock(blob))
    memory=BankedMemory(blocks,cache_slots)
    stats={"observations":len(observations),"complete_contexts":len({canonical(c) for c,_ in observations}),
           "projected_contexts":len({canonical(c) for c,_ in leaves}),"masks":[list(m) for m in masks],"groups":len(blocks),
           "bank_counts":[b.meta()["banks"] for b in blocks],"bank_loads":[b.meta()["counts"] for b in blocks],**memory.storage()}
    return memory,stats
