import copy
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import cell,normalize,to_meaning
from .cases import dataset as legacy_dataset,scene_key
from .integrity import ROOT,read
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin,request,prepare,learn

def cases(seed,development=False):
    lex=read(ROOT/'data/lexicon.json')['slot_candidates'];source=legacy_dataset('ssdoc04-'+str(seed),development)
    result=[]
    for i,c in enumerate(source):
        o=copy.deepcopy(c['known']);n=o['count'];last=f'event:{n-1}'
        pairs=[('event:1/subject','event:1/object'),('event:0/subject',last+'/subject'),
               ('event:0/predicate',last+'/polarity'),('event:0/polarity',last+'/modality'),
               ('time/event:0,event:1',last+'/subject'),('event:0/object',last+'/predicate')]
        a,b=pairs[(i//2)%len(pairs)];targets=[a,b];choices={t:(('unspecified','before','after') if t.startswith('time/') else lex[t.rsplit('/',1)[1]]) for t in targets}
        initial=copy.deepcopy(o);steps=[];old_values={t:[o['cells'][t]['candidates'][0]] for t in targets}
        for j,t in enumerate((a,b,a,b,a) if c['kind']=='focal' else (a,a)):
            previous=o['cells'][t]['candidates'][0]
            # Second background confirmation renews the same value; focal confirmations change it.
            value=previous if c['kind']=='background' and j==1 else choices[t][(choices[t].index(previous)+1)%len(choices[t])]
            old_values[t].append(value);o['cells'][t]=cell('known',[value]);o=normalize(o,lex)
            steps.append({'target':t,'value':value,'operation':'supply' if j==0 or c['kind']=='background' else 'revise','known':copy.deepcopy(o)})
        observation=copy.deepcopy(initial);observation['cells'][a]=cell('ambiguous',[initial['cells'][a]['candidates'][0],steps[0]['value']]);observation=normalize(observation,lex)
        result.append({'id':f'r{seed}/{i}','scope':{'episode':'revision-'+c['episode'],'mutable':targets},'kind':c['kind'],
                       'initial':initial,'observation':observation,'steps':steps,'final':steps[-1]['known'],'history_values':old_values})
    return result

def fresh(case,stage=4,mode='missing'):
    o=copy.deepcopy(case['steps'][stage]['known']);targets=case['scope']['mutable']
    selected=targets[:1] if stage==0 else targets
    if mode in ('only_a','only_b'):selected=[targets[0 if mode=='only_a' else 1]]
    for i,t in enumerate(selected):
        value=o['cells'][t]['candidates'][0]
        alternatives=[v for v in case['history_values'][t] if v!=value]
        if mode=='ambiguous':o['cells'][t]=cell('ambiguous',[value,alternatives[0]])
        elif mode=='conflict' and i==0:o['cells'][t]=cell('conflict',[value,alternatives[0]])
        elif mode=='explicit_old' and i==0:o['cells'][t]=cell('known',[alternatives[0]])
        else:o['cells'][t]=cell('unreadable' if mode=='mixed' and i==1 else 'unobserved',[])
    return o

def prepared_data(model,data):
    memory=RevisionMemory(model.codec.candidates,'none');records=[]
    for case in data:
        p=model.encode(case['observation']);root=begin(model,memory,case['scope'],p,case['kind']=='focal');teachers=[]
        for step in case['steps']:
            message=request(model,memory,case['scope'],p,step['target'],step['value'],step['operation'])
            teacher,local=prepare(model,memory,case['scope'],p,message)
            assert model.recover(local['packet'])['observation']==step['known']
            learn(memory,teacher);p=local['packet'];teachers.append({'prepared':teacher,'message':message,'local_audit':local['audit']})
        records.append({'id':case['id'],'kind':case['kind'],'root':root,'targets':case['scope']['mutable'],'teachers':teachers})
    return records
