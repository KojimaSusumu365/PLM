import copy
from ss_revision.memory import RevisionMemory
from ss_revision.learning import learn
from ss_revision.context import address
from ss_retention.context import domain
from ss_select.runtime import Workset,choose
from ss_select.feedback import answer
from .delay_cases import entries
from .reconfirm_experiment import probe

def initialize(model,records,method,seed):
    m=RevisionMemory(model.codec.candidates,method,seed)
    for r in records:m.register(r['root'],r['targets'],r['kind']=='focal')
    focal=[r for r in records if r['kind']=='focal']
    for step in range(5):
        for r in focal:learn(m,r['teachers'][step]['prepared'])
    return m

def background(memory,records,start,stop):
    rows=[r for r in records if r['kind']=='background'][start:stop];assert len(rows)==stop-start
    for r in rows:
        for teacher in r['teachers']:learn(memory,teacher['prepared'])

def slot_score(memory,cases,records):
    roots={r['id']:r['root'] for r in records};rows=[]
    for c in cases:
        root=roots[c['id']];slots=[]
        for target in c['scope']['mutable']:
            revision=memory.roots[root]['versions'][target]
            raw=memory.ss.recall(address(memory.policy,root,target,revision,c['scope'],c['final']),domain(target));value=raw['value']
            slots.append({'target':target,'value':value,'correct':value==c['final']['cells'][target]['candidates'][0],
                          'wrong':value is not None and value!=c['final']['cells'][target]['candidates'][0]})
        ready=all(s['value'] is not None for s in slots);correct=all(s['correct'] for s in slots)
        rows.append({'id':c['id'],'correct':correct,'wrong':ready and not correct,'held':not ready,'slots':slots})
    return rows

def utility(row):return (2*int(row['correct'])+sum(int(s['correct']) for s in row['slots'])-4*int(row['wrong']))/4

def run_selection(model,memory,cases,policy,selector,budget=6,seed='selection-order-06'):
    work=Workset(model,entries(model,cases));lookup={c['id']:c for c in cases};excluded=[];trace=[]
    sf=selector.fingerprint
    for step in range(budget):
        pick=choose(memory,work,policy,selector,excluded,seed,step);q=pick['question']
        # Only this evaluator-side line can access the chosen target's external answer.
        value=lookup[q['id']]['final']['cells'][q['target']]['candidates'][0]
        receipt=answer(model,memory,work,q,value,excluded);excluded.append([q['id'],q['target']])
        trace.append({'step':step,'selection':pick,'external_answer':value,'receipt':receipt})
    assert len(excluded)==len(set(map(tuple,excluded)))==budget and selector.fingerprint==sf
    return trace

def document_probes(model,memory,cases):
    fp=memory.fingerprint;rows=[];signals={}
    for i,c in enumerate(cases):
        row,source,completed=probe(model,memory,c);rows.append(row)
        if i==0:
            signals['initial']=model.vector(source)
            if completed is not None:signals['completed']=model.vector(completed)
    assert memory.fingerprint==fp;return rows,signals

def branch_confirmation(memory,record,target,value):
    root=record['root'];base=memory.roots[root]['versions'][target]
    # Offline counterfactual corpus construction uses the validated internal prepared-record API.
    return learn(memory,{'root':root,'target':target,'base_revision':base,'revision':base+1,'value':value,
                         'legacy_key':record['teachers'][0]['prepared']['legacy_key']})
