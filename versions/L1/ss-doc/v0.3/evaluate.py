import argparse
import copy
import time
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,verify
from evaluation.cases import dataset,fresh_observation
from evaluation.experiment import teacher_records,train,query,drift_probe
from ss_partial.runtime import PartialModel
from ss_partial.update import request
from ss_partial.contract import to_meaning
from ss_retention.memory import CorrectionMemory,METHODS
from ss_retention.context import key,domain
from ss_retention.learning import teach

def run(out):
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    model=PartialModel.load(ROOT/'model');conditions=[];signals={};regression=[]
    for data_seed in (100,101):
        data=dataset(data_seed);write(out/f'DATA-{data_seed}.json',data);teachers=teacher_records(model,data)
        write(out/f'TEACHERS-{data_seed}.json',teachers);focal=[c for c in data if c['kind']=='focal']
        for code_seed in range(2):
            for load in (64,256):
                for method in METHODS:
                    cid=f'd{data_seed}-c{code_seed}-b{load}-{method}';memory=CorrectionMemory(model.codec.candidates,method,f'retention-code-{code_seed}')
                    immediate,protected_hold=train(memory,teachers,load)
                    memory.save(out/'memories'/cid);saved_fp=memory.fingerprint
                    memory=CorrectionMemory.load(out/'memories'/cid,model.codec.candidates);assert memory.fingerprint==saved_fp
                    primary=[query(model,memory,c,('ambiguous','unobserved','unreadable')[i%3]) for i,c in enumerate(focal)]
                    controls={mode:[query(model,memory,c,mode,outputs=False) for c in (focal if mode in ('other_episode','changed_anchor') else focal[:6])]
                              for mode in ('other_episode','changed_anchor','explicit_new','conflict')}
                    drift=[drift_probe(model,memory,c) for c in focal[:6] if c['target'].split('/')[-1] in ('subject','object','polarity','predicate','modality')]
                    # Isolated revision branch: do not change primary post-background state.
                    revised=CorrectionMemory.load(out/'memories'/cid,model.codec.candidates)
                    revised_cases=[]
                    for c in focal[:6]:
                        p=model.encode(c['known']);teach(model,revised,c['episode'],p,request(p,c['target'],c['alternative'],'revise'))
                        new=copy.deepcopy(c);new['truth']=c['alternative'];new['known']['cells'][c['target']]={'state':'known','candidates':[c['alternative']]}
                        new['meaning']=to_meaning(new['known'],model.codec.candidates);revised_cases.append(new)
                    revisions=[query(model,revised,c) for c in revised_cases]
                    revised.save(out/'revised_memories'/cid)
                    assert memory.fingerprint==saved_fp,'inference_mutated_weights'
                    first=focal[0];packet=model.encode(fresh_observation(first,'ambiguous'));signals[cid+'-initial']=model.vector(packet)
                    from ss_retention.runtime import complete
                    done=complete(model,memory,first['episode'],packet)
                    if 'packet' in done:signals[cid+'-completed']=model.vector(done['packet'])
                    write(out/'conditions'/(cid+'.json'),{'id':cid,'data_seed':data_seed,'code_seed':code_seed,'background_load':load,'method':method,
                          'immediate':immediate,'protected_coefficients_unchanged':protected_hold,'memory_fingerprint':saved_fp,
                          'primary':primary,'controls':controls,'unobserved_world_change':drift,'revisions':revisions,'revised_fingerprint':revised.fingerprint,
                          'inference_weights_unchanged':True,'cost':memory.cost(),'eligible_for_inference':False})
                    conditions.append(cid);print(cid+' complete',flush=True)
    # Existing complete text output remains current observation, not overwritten by an empty episodic memory.
    from ss_partial.reader import read as read_text
    from ss_retention.runtime import generate
    from evaluation.oracle import scored,localize
    empty=CorrectionMemory(model.codec.candidates,'none')
    for c in read(ROOT/'data/doc_v01_regression.json'):
        r=read_text(model,[c['text']]);row={'id':c['id'],'read_status':r['status']}
        if 'packet' in r:
            g=generate(model,empty,'regression/'+c['id'],r['packet'],'reverse');n=len(c['meaning']['events'])
            row['output']=g;row['score']=scored(localize(c['meaning'],c['meaning']['presentation'][::-1],['subject']*n),g.get('text',''))
        regression.append(row)
    np.savez_compressed(out/'REFERENCE_SIGNALS.npz',**signals)
    write(out/'INDEX.json',{'conditions':conditions,'frozen_source_digest':frozen,'reference_arrays':len(signals),'eligible_for_inference':False})
    write(out/'REGRESSION.json',regression);write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start})
    print('COMPLETE '+str(len(conditions))+' conditions',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
