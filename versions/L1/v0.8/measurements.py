"""Request-level, independent event/time scoring; diagnostics do not tune the model."""
import copy
import hashlib
import json
import numpy as np
from plm_l1_v06.algebra import canonical
from plm_l1_v08.contract import IDS,PRESENTATIONS,TIMES,write_context,split_document
from plm_l1_v08.codec import TemporalCodec
from plm_l1_v08.training import fit
from evaluation_support import data,GOALS,CATEGORIES,parse,expected,to_mentions,unique_meanings

STAGES=('read','generate','roundtrip')
INVALID_TEXTS=(
    '', '太郎が花子を助けた。', '太郎が花子を助けた。花子が太郎を助けた。健太が花子を褒めた。',
    '太郎が花子を助けた。その後、彼が太郎を助けた。',
    '太郎が花子を助けた。だから、花子が太郎を助けた。',
    '太郎が花子を助けた。同時に、花子が太郎を助けた。',
    'その後、太郎が花子を助けた。花子が太郎を助けた。',
    '太郎が花子を助けた。その後、その前に、花子が太郎を助けた。',
    '太郎が花子を助けた。その後花子が太郎を助けた。',
    '太郎が花子を助けた。その後、',
    '太郎が花子を助けた。その後、花子が太郎を助けた',
    '太郎 が花子を助けた。その後、花子が太郎を助けた。',
    '太郎が花子を助けた。その後、未知が太郎を助けた。',
    '太郎が花子を助けた。花子が太郎を助けた。。',
    '太郎が花子を助けた。、花子が太郎を助けた。',
    '太郎が花子を助けた。その後、花子が太郎を助けた。余分',
    'x'*551)


def count(records,stages=STAGES):
    result={}
    for stage in stages:
        rows=[r for r in records if r['stage']==stage]
        accepted=sum(bool(r['accepted']) for r in rows); exact=sum(bool(r['exact']) for r in rows)
        result[stage]={'requests':len(rows),'accepted':accepted,'exact':exact,'wrong':accepted-exact,'abstained':len(rows)-accepted}
    return result


def bad_packets(model,meaning):
    p=model.encode(meaning)
    result=[None,{},[],dict(p,gold=meaning),dict(p,events=meaning['events']),dict(p,temporal=meaning['temporal']),
            dict(p,schema='plm-two-event-signal-v1'),dict(p,model_fingerprint='wrong'),dict(p,eligible_for_inference=True),
            dict(p,dimension=True),dict(p,dimension=model.codec.dimension+128),dict(p,real=p['real'][:-1]),
            dict(p,real=[False]+p['real'][1:]),dict(p,real=[float('nan')]+p['real'][1:]),
            dict(p,imag=[float('inf')]+p['imag'][1:]),dict(p,real=[33.]+p['real'][1:])]
    return result


def assess(model,rows,roundtrip=True):
    records=[]
    for row in rows:
        out=model.read(row['text']); accepted=out['status']=='read'
        recovered=model.recover(out['packet']) if accepted else None
        actual=recovered.get('meaning') if recovered else None
        gold=to_mentions(row['meaning']); exact=accepted and actual==gold
        records.append({'stage':'read','id':row['id'],'category':row['category'],'accepted':accepted,'exact':exact,
                        'temporal_kind':gold['temporal']['kind'],'reason':out.get('reason'),'actual_meaning':actual})
        if roundtrip:
            for order in ('preserve','reverse'):
                for gi,goals in enumerate(GOALS):
                    generated=model.generate(out['packet'],goals,order) if accepted else {'status':'abstain','reason':'read_abstained'}
                    parsed=parse(generated.get('text')); success=generated['status']=='generated'
                    target=expected(row['meaning'],goals,order)
                    records.append({'stage':'roundtrip','id':row['id']+f'/{order}/{gi}','category':row['category'],
                                    'order':order,'temporal_kind':gold['temporal']['kind'],'accepted':success,
                                    'exact':success and parsed==target,'events_exact':bool(parsed and parsed['events']==target['events']),
                                    'relation_exact':bool(parsed and parsed['relation']==target['relation']),
                                    'text':generated.get('text'),'reason':generated.get('reason')})
    for row in unique_meanings(rows):
        packet=model.encode(row['meaning'])
        for order in ('preserve','reverse'):
            for gi,goals in enumerate(GOALS):
                out=model.generate(packet,goals,order); accepted=out['status']=='generated'
                target=expected(row['meaning'],goals,order); parsed=parse(out.get('text'))
                records.append({'stage':'generate','id':row['id']+f'/{order}/{gi}','category':row['category'],
                                'order':order,'temporal_kind':row['meaning']['temporal']['kind'],'accepted':accepted,
                                'exact':accepted and parsed==target,'events_exact':bool(parsed and parsed['events']==target['events']),
                                'relation_exact':bool(parsed and parsed['relation']==target['relation']),
                                'text':out.get('text'),'reason':out.get('reason')})
    return {'counts':count(records),'records':records,
            'categories':{c:count([r for r in records if r['category']==c]) for c in CATEGORIES},
            'invalid_texts':[{'text':text,'status':model.read(text)['status']} for text in INVALID_TEXTS],
            'invalid_packets':[model.generate(p)['status'] for p in bad_packets(model,rows[0]['meaning'])]}


def codec_probe(candidates,rows,dimension,seed,mode):
    codec=TemporalCodec(candidates,dimension,seed,mode)
    records=[]
    for row in unique_meanings(rows):
        meaning=row['meaning']; vector=codec.encode(meaning)
        try:
            actual=codec.recover(vector)['meaning']; accepted=True; reason=None
        except ValueError as error:
            actual=None; accepted=False; reason=str(error)
        reverse=copy.deepcopy(meaning)
        if reverse['temporal']['kind']=='before':
            reverse['temporal']['source'],reverse['temporal']['target']=reverse['temporal']['target'],reverse['temporal']['source']
            same=bool(np.array_equal(vector,codec.encode(reverse)))
        else: same=None
        reorder=copy.deepcopy(meaning); reorder['presentation'].reverse()
        records.append({'stage':'codec','id':row['id'],'accepted':accepted,'exact':accepted and actual==meaning,
                        'reason':reason,'temporal_kind':meaning['temporal']['kind'],'reversed_edge_same_signal':same,
                        'reordered_presentation_same_signal':bool(np.array_equal(vector,codec.encode(reorder)))})
    return {'dimension':dimension,'seed':seed,'mode':mode,'payload_bytes':16*dimension,'counts':count(records,('codec',))['codec'],'records':records}


def noise_rng(seed):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8],'little'))


def noise_probe(candidates,rows,dimension,seed,level):
    codec=TemporalCodec(candidates,dimension,seed)
    rng=noise_rng(seed); records=[]
    for row in unique_meanings(rows):
        vector=codec.encode(row['meaning'])
        noise=rng.normal(size=dimension)+1j*rng.normal(size=dimension)
        noisy=vector+noise/np.linalg.norm(noise)*np.linalg.norm(vector)*level
        try:
            actual=codec.recover(noisy)['meaning']; accepted=True; reason=None
        except ValueError as error:
            actual=None; accepted=False; reason=str(error)
        records.append({'stage':'noise','id':row['id'],'accepted':accepted,'exact':accepted and actual==row['meaning'],'reason':reason})
    return {'dimension':dimension,'seed':seed,'level':level,'counts':count(records,('noise',))['noise'],'records':records}


def learning_controls(rows):
    train=data('temporal_train'); component=data('component_train'); lex=data('lexicon')
    sample=unique_meanings(rows)
    result={}
    for mode in ('no_learning','flipped_teacher','renamed_markers','without_after'):
        pairs=copy.deepcopy(train)
        if mode=='flipped_teacher':
            for p in pairs:
                t=p['meaning']['temporal']
                if t['kind']=='before': t['source'],t['target']=t['target'],t['source']
        elif mode=='renamed_markers':
            for p in pairs: p['text']=p['text'].replace('その後、','記号甲、').replace('その前に、','記号乙、')
        elif mode=='without_after': pairs=[p for p in pairs if 'その前に、' not in p['text']]
        m=fit(component,pairs,lex,seed='temporal-control-'+mode,learning=mode!='no_learning')
        records=[]
        for row in sample:
            text=row['text']; gold=to_mentions(row['meaning'])
            if mode=='flipped_teacher' and gold['temporal']['kind']=='before':
                t=gold['temporal']; t['source'],t['target']=t['target'],t['source']
            if mode=='renamed_markers': text=text.replace('その後、','記号甲、').replace('その前に、','記号乙、')
            r=m.read(text); accepted=r['status']=='read'; actual=m.recover(r['packet']).get('meaning') if accepted else None
            missing=mode=='without_after' and 'その前に、' in text
            records.append({'stage':'read','id':row['id'],'accepted':accepted,'exact':accepted and actual==gold,
                            'expected_abstain':mode=='no_learning' or missing,'reason':r.get('reason')})
            for order in ('preserve','reverse'):
                out=m.generate(m.encode(row['meaning']),['subject','subject'],order); success=out['status']=='generated'
                output=out.get('text')
                if output and mode=='renamed_markers': output=output.replace('記号甲、','その後、').replace('記号乙、','その前に、')
                target=expected(row['meaning'],['subject','subject'],order)
                if mode=='flipped_teacher' and target['relation']!='unknown': target['relation']='after' if target['relation']=='before' else 'before'
                missing=mode=='without_after' and target['relation']=='after'
                records.append({'stage':'generate','id':row['id']+'/'+order,'accepted':success,'exact':success and parse(output)==target,
                                'expected_abstain':mode=='no_learning' or missing,'reason':out.get('reason')})
        result[mode]={'records':records,'counts':count(records,('read','generate'))}
    # Exact table is only a relation-lookup reference, not an equal-RAM full NLP baseline.
    table_read={}; table_write={}
    for p in train:
        _,marker=split_document(p['text']); order=p['meaning']['presentation']; time=p['meaning']['temporal']
        table_read[canonical({'marker':marker,'presentation':order})]=time
        table_write[canonical(write_context(time,order))]=marker
    records=[]
    for row in rows:
        clauses,marker=split_document(row['text']); gold=to_mentions(row['meaning'])
        q=canonical({'marker':marker,'presentation':list(IDS)})
        records.append({'id':row['id'],'read_exact':table_read.get(q)==gold['temporal'],
                        'write_exact':all(table_write.get(canonical(write_context(row['meaning']['temporal'],order)))==
                           {'unknown':'','before':'その後、','after':'その前に、'}[expected(row['meaning'],GOALS[0],choice)['relation']]
                           for choice,order in (('preserve',row['meaning']['presentation']),('reverse',list(reversed(row['meaning']['presentation'])))))})
    result['relation_table_reference']={'scope':'relation lookup only, not full NLP or matched-memory/speed comparison','read_keys':len(table_read),
                                       'write_keys':len(table_write),'records':records}
    return result
