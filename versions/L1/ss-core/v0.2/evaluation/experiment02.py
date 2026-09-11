import copy
import numpy as np
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import from_meaning,to_meaning
from ss_revision.memory import RevisionMemory
from ss_revision.context import scope_key,address
from ss_retention.context import domain
from ss_core.memory import WaveRevisionView
from ss_core.learning import learn_packet as old_learn_packet
from ss_core_v02.store import Store,scope_id
from ss_core_v02.transaction import apply_packet
from bridge.carrier import encode
from bridge.runtime import receive
from .integrity import ROOT,read,write
from .prior_experiment import finish,compact
from .faults import Acquisitions
from .ports import factory as old_factory

def prepare_inputs(model,cases):
    packets={};records=[]
    for c in cases:
        for kind in ('initial','final','query'):
            if kind=='query':observation=c['query']
            else:
                text=c['initial_text'] if kind=='initial' else c['text']
                r=model.document.read(text);assert r['status']=='read'
                observation=from_meaning(model.document.recover(r['packet'])['meaning'],model.codec.candidates)
            expected=c['initial'] if kind=='initial' else c['known'] if kind=='final' else c['query']
            assert observation==expected
            mid='guard02/'+c['id']+'/'+kind
            wire=encode(model,model.encode(observation),mid)
            r=receive(model,wire,mid)
            packets[(c['id'],kind)]=r.get('packet')
            actual=model.recover(r['packet'])['observation'] if r['status']=='received' else None
            records.append({'case_id':c['id'],'kind':kind,'message_id':mid,'wire_sha256':digest(wire),
                            'reception':compact(r),'observation_equal':actual==expected})
    return packets,records

def score(model,store,case,packet):
    before=store.fingerprint
    if scope_id(case['scope']) in store.pending:
        return {'status':'held','failure_stage':'pending_reconfirmation','correct':False,'wrong':False,
                'outputs':[],'requested_outputs':2,'fresh_session_no_receipts':True,'nonmutable_changed':False}
    view=WaveRevisionView(store.memory,chunk=37)
    r=finish(model,view,case['scope'],{'status':'received','packet':packet,'stage':'ready'},case)
    assert store.fingerprint==before
    return r

def base_store(model,cases,packets,seed):
    store=Store(RevisionMemory(model.codec.candidates,'versioned_pair','guard02-memory-'+str(seed)))
    records=[]
    for c in cases:
        if c['kind']=='background':continue
        store,r=apply_packet(model,store,c['scope'],packets[(c['id'],'initial')],method='single')
        records.append({'case_id':c['id'],'receipt':r})
    return store,records

def followup(model,store,cases,packets):
    receipts=[]
    for c in cases:
        if c['kind']!='background':continue
        store,r=apply_packet(model,store,c['scope'],packets[(c['id'],'final')],False,method='single')
        receipts.append({'case_id':c['id'],'receipt':r})
    return store,receipts

def bias_mapping(memory,case):
    root,targets=scope_key(case['scope'],case['known'])
    return {address(memory.policy,root,t,memory.roots[root]['versions'][t]+1):
            (domain(t),case['known']['cells'][t]['candidates'][0]) for t in targets}

def trial(model,base,cases,packets,case,anchor,seed,condition,method,out):
    before=base.fingerprint
    port=Acquisitions(condition,61000+seed*101+int(case['id'].split('/')[-1])*1009,bias_mapping(base.memory,case))
    updated,receipt=apply_packet(model,base,case['scope'],packets[(case['id'],'final')],method=method,port_factory=port)
    updated.save(out/'after')
    cold=Store.load(out/'after',model.codec.candidates)
    immediate=score(model,cold,case,packets[(case['id'],'query')])
    delayed,following=followup(model,cold,cases,packets)
    delayed.save(out/'later')
    loaded=Store.load(out/'later',model.codec.candidates)
    later=score(model,loaded,case,packets[(case['id'],'query')])
    retained=score(model,loaded,anchor,packets[(anchor['id'],'query')])
    assert base.fingerprint==before
    committed=receipt['status']=='learned'
    failed_new=not immediate['correct'] or not later['correct']
    return {'case_id':case['id'],'anchor_id':anchor['id'],'seed':seed,'condition':condition,'method':method,
            'receipt':receipt,'acquisitions':port.records,'committed':committed,
            'committed_but_target_not_correct':committed and failed_new,
            'held_correct_teacher':not committed,'ss_memory_unchanged_on_hold':committed or updated.memory.fingerprint==base.memory.fingerprint,
            'pending_after':len(updated.pending),'immediate':immediate,'later':later,'anchor':retained,
            'following':following,'after_fingerprint':updated.fingerprint,'later_fingerprint':loaded.fingerprint,
            'cost':receipt.get('cost',{'read_windows_started':0,'read_ticks_processed':0,'write_ticks_acknowledged':0}),
            'eligible_for_inference':False}

def historical(model,new_cases,new_packets,out):
    old_cases=[c for c in read(ROOT/'data/CORPUS.json')['splits']['evaluation'] if c['kind']=='focal']
    reference=read(ROOT/'data/CORE01_UPDATE_FAULTS.json')
    rows=[]
    for seed in (0,1,2):
        memory=RevisionMemory.load(ROOT/'data/CORE01_MEMORIES'/str(seed),model.codec.candidates)
        c=old_cases[0]
        noisy,r=old_learn_packet(model,memory,c['scope'],model.encode(c['known']),port_factory=old_factory('payload_noise',seed))
        original=next(x for x in reference if x['seed']==seed and x['condition']=='payload_noise')
        assert r['after_memory']==original['receipt']['after_memory'], 'historical_update_not_identical'
        for mode,m in [('noisy',noisy),('clean_reference',old_learn_packet(model,memory,c['scope'],model.encode(c['known']))[0])]:
            store=Store(m)
            for stage in ('after','later'):
                if stage=='later':store,_=followup(model,store,new_cases,new_packets)
                path=out/f'{seed}-{mode}-{stage}'
                store.save(path)
                cold=Store.load(path,model.codec.candidates)
                scores=[{'case_id':case['id'],'result':score(model,cold,case,model.encode(case['query']))} for case in old_cases]
                rows.append({'seed':seed,'mode':mode,'stage':stage,'store':path.name,'fingerprint':cold.fingerprint,
                             'historical_corrupt_update_fingerprint_exact':True,'scores':scores})
    return rows
