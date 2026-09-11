import copy
import numpy as np
from .support import data,parse,expected,to_mentions
from .metrics import score
from plm_l1_v010.base.component.algebra import canonical

def confounded(row):
    m=row['meaning']
    return (m['polarity']=='polarity:negative')==(m['modality']=='modality:hypothetical')

def training_case(after=False):
    train=[r for r in data('component_train') if confounded(r)]
    val=[r for r in data('single_development') if confounded(r)]
    time=[r for r in data('temporal_train') if all(confounded({'meaning':e}) for e in r['meaning']['events'])]
    added=[r for r in data('component_train') if r['text'] in ('太郎が花子を助けなかった。','もし太郎が花子を助けたら。')]
    assert len(added)==2 and not any(confounded(r) for r in added)
    return train+(added if after else []),val,time

def storage(model):
    blocks=sum(len(b.blob) for member in model.members for group in (member.component.memories,member.memories) for m in group.values() for b in m.blocks)
    caches=sum(len(m.cache) for member in model.members for group in (member.component.memories,member.memories) for m in group.values())
    seen=set()
    def arrays(value):
        if isinstance(value,np.ndarray):
            if id(value) in seen:return 0
            seen.add(id(value)); return value.nbytes
        if isinstance(value,dict):return sum(arrays(v) for v in value.values())
        if isinstance(value,(list,tuple)):return sum(arrays(v) for v in value)
        return 0
    payload=sum(arrays(m.codec.__dict__)+arrays(m.component.basis)+arrays(m.component.book.cache) for m in model.members)
    return {'members':len(model.members),'phase_block_bytes':blocks,'fixed_recall_cache_bytes':caches,'codec_and_component_array_payload_bytes':payload,
            'known_payload_total_bytes':blocks+caches+payload,'scope':'Warm owned payloads; excludes Python container/object overhead, interpreter, libraries, training temporaries and OS RSS.'}

def standard(model,rows,full=True):
    reads=[]; gold=[]; roundtrips=[]; demos=[]
    for i,row in enumerate(rows):
        target=to_mentions(row['meaning']); out=model.read(row['text']); gold.append(target)
        recovered=model.recover(out['packet']).get('meaning') if out['status']=='read' else None; reads.append(recovered)
        wanted=expected(target,('object','subject'),'reverse')
        generated=model.generate(out['packet'],('object','subject'),'reverse') if out['status']=='read' else {'status':'abstain'}
        again=model.read(generated['text']) if generated['status']=='generated' else {'status':'abstain'}
        value=model.recover(again['packet']).get('meaning') if again['status']=='read' else None
        ok=value is not None and parse(generated['text'])==wanted and expected(value,('object','subject'))==wanted
        roundtrips.append('correct' if ok else None if generated['status']!='generated' or value is None else 'wrong')
        if i<3:demos.append({'input':row['text'],'output':generated.get('text'),'exact':ok})
        if full and (i+1)%216==0: print('language read/roundtrip',i+1,'/',len(rows),flush=True)
    meanings={canonical(r['meaning']):r['meaning'] for r in rows}; outputs=[]; targets=[]
    for m in meanings.values():
        for order in ('preserve','reverse'):
            g=model.generate(model.encode(m),('subject','object'),order)
            outputs.append(parse(g['text']) if g['status']=='generated' else None); targets.append(expected(m,('subject','object'),order))
    return {'read':score(reads,gold),'direct_generation':score(outputs,targets),'roundtrip':score(roundtrips,['correct']*len(roundtrips)),
            'unique_input_texts':len({r['text'] for r in rows}),'unique_meanings':len(meanings),'storage':storage(model),'demos':demos,
            'member_count':len(model.members),'supported':model.meta['training']['supported']}

def baseline_rows(rows):
    selected={}
    for r in rows:
        key=canonical([r['category'],r['meaning']['temporal'],r['meaning']['presentation']])
        selected.setdefault(key,r)
    return list(selected.values())

def ambiguity_probe(model,split):
    # 9 existing category representatives, both events and two cross-statuses.
    by_category={}
    for r in data(split):by_category.setdefault(r['category'],r['meaning'])
    outputs=[]; targets=[]; details=[]
    for category,meaning in by_category.items():
        for index in (0,1):
            for polarity,modality in (('negative','asserted'),('positive','hypothetical')):
                m=copy.deepcopy(meaning)
                for e in m['events']: e['polarity']='polarity:positive'; e['modality']='modality:asserted'
                m['events'][index]['polarity']='polarity:'+polarity; m['events'][index]['modality']='modality:'+modality
                out=model.generate(model.encode(m),('subject','subject'))
                wanted=expected(m,('subject','subject'))
                outputs.append(parse(out['text']) if out['status']=='generated' else None); targets.append(wanted)
                details.append({'category':category,'changed_event_index':index,'meaning':m,'status':out['status'],
                                'reason':out.get('reason'),'text':out.get('text'),'candidate_audit':out.get('candidate_audit'),
                                'independent_semantic_match':outputs[-1]==wanted})
    return {'generation':score(outputs,targets),'details':details,'selected_masks':model.meta['training']['selected_masks'],
            'component_training_pairs':model.meta['training']['component_pairs'],'selection_validation_pairs':model.meta['training']['selection_pairs'],
            'temporal_training_pairs':model.meta['training']['temporal_pairs'],'storage':storage(model)}
