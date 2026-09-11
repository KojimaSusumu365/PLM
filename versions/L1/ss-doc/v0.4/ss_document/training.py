"""Reuse v0.9 SS learning; three-event composition is a designed extension."""
from plm_l1_v09.training import fit
from plm_l1_v09.runtime import TemporalModel
from plm_l1_v09.component.runtime import Model
from plm_l1_v09.component.banked import BankedMemory,MemoryBlock,META_BYTES
from .runtime import DocumentModel


def train(component_pairs,temporal_pairs,lexicon,**kwargs):
    base=fit(component_pairs,temporal_pairs,lexicon,seed='temporal-evaluation-0',selection_seed='selection-evaluation-0',selector='ss')
    return DocumentModel(base,**kwargs)


def zero(memory):
    return BankedMemory([MemoryBlock(b.blob[:META_BYTES]+bytes(len(b.blob)-META_BYTES)) for b in memory.blocks])


def variant(base,dimension=8192,seed='ssdoc-code-0',mode='bound',condition='normal'):
    if condition in ('zero_temporal_read','zero_temporal_write'):
        memories=dict(base.memories);name=condition.removeprefix('zero_');memories[name]=zero(memories[name])
        base=TemporalModel(base.component,memories,base.meta['training'],dimension=base.meta['dimension'],seed=base.meta['seed'],mode=base.meta['mode'])
    elif condition=='zero_lexical_write':
        memories=dict(base.component.memories);memories['lexical_write']=zero(memories['lexical_write'])
        component=Model(base.component.meta,memories)
        base=TemporalModel(component,base.memories,base.meta['training'],dimension=base.meta['dimension'],seed=base.meta['seed'],mode=base.meta['mode'])
    return DocumentModel(base,dimension,seed,mode,condition)
