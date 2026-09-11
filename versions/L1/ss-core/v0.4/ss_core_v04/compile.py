"""Offline signal-code alignment teachers. Never imported by the generation core."""
import hashlib,json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.banked import FreshBook
from plm_l1_v09.component.lexicon import ROLES
from plm_l1_v09.component.algebra import canonical
from plm_l1_v09.contract import write_context
from ss_partial.runtime import PartialModel
from ss_core_v03.program import Program
from ss_core_v03.waveform import Engine

def compile_bundle(root,destination):
    root,destination=Path(root),Path(destination)
    model=PartialModel.load(root/'model');doc=model.document;codec=doc.codec
    n=codec.dimension;b=FreshBook(n,'ssdoc-v01/'+codec.seed);own=FreshBook(n,'working04')
    sentence=Program.load(root/'programs/sentence',Engine())
    document=Program.load(root/'programs/document',Engine())
    labels=list(dict.fromkeys(v for r in ROLES for v in codec.candidates[r]))
    values=[b.code('value',v) for v in labels]
    events=np.array([b.code('occurrence',x) for x in ('event:0','event:1')])
    roles=np.array([b.code('role',x) for x in ROLES])
    addresses=[e*r for e in events for r in roles]
    names=[i+'/'+r for i in ('event:0','event:1') for r in ROLES]
    domains=[list(codec.candidates[r]) for _ in range(2) for r in ROLES]
    time_address=b.code('time_pair',['event:0','event:1'])
    order_address=own.code('address','presentation')
    addresses.extend([time_address,order_address]);names+=['time/event:0,event:1','presentation']
    for i,ref in enumerate(codec.relations[('event:0','event:1')]):
        labels.append(('unspecified','before','after')[i]);values.append(ref*time_address.conj())
    for i,ref in enumerate(codec.order_codes[2]):
        labels.append('order:'+str(i));values.append(ref*order_address.conj())
    domains += [['unspecified','before','after'],['order:0','order:1']]
    values=np.array(values);addresses=np.array(addresses)
    states=np.array([own.code('state',i) for i in range(5)])
    arities=np.array([own.code('arity',i) for i in range(7)])
    arrays={'values':values,'addresses':addresses,'states':states,'arities':arities,'events':events,'roles':roles,
            'header':codec.counts[0]+codec.presence[0]+codec.presence[1],
            'known_status':sum(a*(states[0]+arities[1]) for a in addresses),
            'global_addresses':np.array([time_address,order_address]),
            'sentence_weights':sentence.weights,'sentence_actions':sentence.actions,'sentence_states':sentence.states,
            'document_weights':document.weights,'document_actions':document.actions,'document_states':document.states,
            'goal_signals':np.array([sentence.book.code('context/goal',g) for g in ('subject','object')]),
            'order_signals':np.array([document.book.code('context/order',o) for o in ('preserve','reverse')])}
    surfaces=sorted({*model.document.base.component.meta['kinds'],*model.document.base.meta['training']['marker_inventory']})
    surface_codes=np.array([own.code('surface',s) for s in surfaces]);arrays['surfaces']=surface_codes
    operations=np.array([own.code('operation',i) for i in range(3)]) # lexical/event, literal, stop
    arrays['operations']=operations
    null=own.code('operand','null')
    counts={};write_ticks=0
    def add(name,pairs,refs):
        nonlocal write_ticks
        # Teachers with exactly the same input/output contribute once.
        unique={}
        for key,value in pairs:
            ident=hashlib.sha256(key.tobytes()).hexdigest()
            if ident in unique:assert np.array_equal(unique[ident][1],value)
            unique[ident]=(key,value)
        w=np.zeros(n,complex)
        for key,value in unique.values():
            for j in range(n):w[j]+=key[j].conjugate()*value[j]
        arrays[name+'_weights']=w;arrays[name+'_refs']=np.array(refs)
        counts[name]=len(unique);write_ticks+=len(unique)*n
    allowed=np.zeros(n,complex)
    for addr,domain in zip(addresses,domains):
        for label in domain:
            for j in range(n):allowed[j]+=addr[j].conjugate()*values[labels.index(label),j]
            write_ticks+=n
    arrays['allowed']=allowed
    for field in ('polarity','modality'):
        refs=[sentence.book.code('context/'+field,x) for x in codec.candidates[field]]
        add(field,[(values[labels.index(x)],ref) for x,ref in zip(codec.candidates[field],refs)],refs)
    presentation_refs=[document.book.code('context/presentation',x) for x in codec.orders[2]]
    add('presentation',[(values[labels.index('order:'+str(i))],ref) for i,ref in enumerate(presentation_refs)],presentation_refs)
    pairs=[]
    for label in labels:
        if label not in set(codec.candidates['subject'])|set(codec.candidates['predicate']):continue
        surface=doc.base.component.memories['lexical_write'].recall({'meaning_value':label})['value']
        assert surface is not None
        pairs.append((values[labels.index(label)],surface_codes[surfaces.index(surface)]))
    add('lexical',pairs,surface_codes)
    pairs=[]
    for ti,relation in enumerate(codec.relation_values[('event:0','event:1')]):
        temporal={k:relation[k] for k in ('kind','source','target')}
        for first in range(2):
            ids=['event:'+str(first),'event:'+str(1-first)]
            selected=doc.base.memories['temporal_write'].recall(write_context(temporal,ids))['value']
            assert selected is not None
            marker=json.loads(selected)
            pairs.append((values[labels.index(('unspecified','before','after')[ti])]*events[first],surface_codes[surfaces.index(marker)]))
    add('temporal',pairs,surface_codes)
    operands=np.concatenate([roles,surface_codes,null[None,:]])
    op_pairs=[];operand_pairs=[]
    for action,code in zip(sentence.meta['actions'],sentence.actions):
        if action=='stop':op,operand=2,null
        elif action.startswith('lexical:'):op,operand=0,roles[ROLES.index(action[8:])]
        else:op,operand=1,surface_codes[surfaces.index(action[6:])]
        op_pairs.append((code,operations[op]));operand_pairs.append((code,operand))
    add('sentence_op',op_pairs,operations);add('sentence_operand',operand_pairs,operands)
    op_pairs=[];operand_pairs=[]
    for action,code in zip(document.meta['actions'],document.actions):
        if action=='stop':op,operand=2,null
        else:op,operand=0,events[int(action.rsplit(':',1)[1])]
        op_pairs.append((code,operations[op]));operand_pairs.append((code,operand))
    add('document_op',op_pairs,operations);add('document_operand',operand_pairs,np.concatenate([events,null[None,:]]))
    destination.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(destination/'signals.npz',**arrays)
    meta={'schema':'signal-working-bundle04','width':n,'source_fingerprint':doc.fingerprint,'surfaces':surfaces,
          'array_hashes':{k:hashlib.sha256(a.astype('<c16').tobytes()).hexdigest() for k,a in arrays.items()}}
    (destination/'bundle.json').write_text(canonical(meta)+'\n',encoding='utf-8')
    (destination/'IO.json').write_text(canonical({'addresses':names,'values':labels,'domains':domains,
         'states':['known','ambiguous','unobserved','unreadable','conflict']})+'\n',encoding='utf-8')
    report={'association_teachers':counts,'schema_domain_pairs':sum(map(len,domains)),'write_ticks':write_ticks,
            'array_bytes':sum(a.nbytes for a in arrays.values()),
            'learned_new_weight_bytes':sum(a.nbytes for k,a in arrays.items() if k.endswith('_weights') and not k.startswith(('sentence_weights','document_weights')))+allowed.nbytes,
            'no_new_grammar_learning':True,'source':'v03 frozen learned lexical/temporal maps and designed code alignments'}
    (destination/'TRAINING.json').write_text(canonical(report)+'\n',encoding='utf-8')
    return report
