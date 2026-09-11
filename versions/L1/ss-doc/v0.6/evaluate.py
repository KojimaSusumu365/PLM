import argparse,copy,time
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,verify
from evaluation.delay_cases import audit
from evaluation.revision_cases import prepared_data
from evaluation.delay_experiment import initialize,background,slot_score,run_selection,document_probes
from evaluation.reconfirm_experiment import failure_regression
from evaluation.oracle import localize,scored
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_select.memory import SelectorMemory

def run(out):
    frozen=verify();start=time.perf_counter();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    plan=read(ROOT/'evaluation/PROTOCOL.json');data=read(ROOT/'data/DELAY_DATASETS.json');model=PartialModel.load(ROOT/'model')
    selector=SelectorMemory.load(ROOT/'data/selector_model');selector_fp=selector.fingerprint;conditions=[];bases=[];signals={}
    write(out/'DATA_AUDIT.json',audit(data,read(ROOT/'data/DELAY_EXCLUSIONS.json')))
    for split in plan['evaluation_splits']:
        ds=data['splits'][split];records=prepared_data(model,ds['cases']);focal=[ds['cases'][i] for i in ds['order']]
        write(out/f'TEACHERS-{split}.json',records);print({'prepared':split},flush=True)
        for code_i,seed in enumerate(plan['evaluation_code_seeds']):
            for method in plan['memory_methods']:
                memory=initialize(model,records,method,seed);previous=0
                for load in plan['background_levels']:
                    background(memory,records,previous,load);previous=load;bid=f'd{split}-c{code_i}-{method}-l{load}';bases.append(bid)
                    memory.save(out/'base_memories'/bid);before=slot_score(memory,focal,records);control=copy.deepcopy(memory)
                    background(control,records,load,load+plan['delayed_background']);delayed=slot_score(control,focal,records)
                    write(out/'baselines'/(bid+'.json'),{'base':bid,'memory_fingerprint':memory.fingerprint,'before':before,'delayed':delayed,
                          'delayed_memory_fingerprint':control.fingerprint,'external_reconfirmations':0,'text_generation_measured':False})
                    for policy in plan['selection_policies']:
                        cid=bid+'-'+policy;current=copy.deepcopy(memory);trace=run_selection(model,current,focal,policy,selector,plan['exact_confirmation_budget'],bid)
                        immediate=slot_score(current,focal,records);answer_fp=current.fingerprint;current.save(out/'after_answers_memories'/cid)
                        background(current,records,load,load+plan['delayed_background']);fp=current.fingerprint;current.save(out/'memories'/cid)
                        final=RevisionMemory.load(out/'memories'/cid,model.codec.candidates);assert final.fingerprint==fp
                        rows,reference=document_probes(model,final,focal);slots=slot_score(final,focal,records)
                        assert all((a['correct'],a['wrong'])==(b['correct'],b['wrong']) for a,b in zip(rows,slots))
                        for name,value in reference.items():signals[cid+'-'+name]=value
                        write(out/'conditions'/(cid+'.json'),{'condition':cid,'base':bid,'split':split,'code':seed,'method':method,'load':load,'policy':policy,
                          'actual_confirmations':len(trace),'required_confirmations':sum(t['selection']['question']['required_now'] for t in trace),
                          'trace':trace,'immediate':immediate,'delayed':rows,'delayed_slots':slots,'after_answers_fingerprint':answer_fp,'memory_fingerprint':fp,
                          'cost':final.cost(),'selector_cost':selector.cost() if policy=='ss_learned' else {'coefficient_bytes':0,'feature_basis_bytes':0,'updates':0},
                          'selector_fingerprint':selector_fp if policy=='ss_learned' else None,'eligible_for_inference':False})
                        assert selector.fingerprint==selector_fp;conditions.append(cid)
                        print({'condition':cid,'answers':len(trace),'immediate_correct':sum(x['correct'] for x in immediate),
                               'delayed_correct':sum(x['correct'] for x in rows),'delayed_wrong':sum(x['wrong'] for x in rows)},flush=True)
    write(out/'V04_FAILURE_REGRESSION.json',failure_regression(model));regression=[]
    for r in read(ROOT/'data/doc_v01_regression.json'):
        m=r['meaning'];goals=['subject']*len(m['events']);g=model.document.generate(model.document.encode(m),'preserve',goals)
        score=scored(localize(m,m['presentation'],goals),g.get('text'));assert score['semantic_equal'];regression.append({'text':g.get('text'),'score':score})
    write(out/'LANGUAGE_REGRESSION.json',regression);np.savez_compressed(out/'REFERENCE_SIGNALS.npz',**signals)
    write(out/'INDEX.json',{'conditions':conditions,'bases':bases,'delayed_probes':len(conditions)*12,'requested_text_outputs':len(conditions)*24,
          'actual_reconfirmations':len(conditions)*plan['exact_confirmation_budget'],'independent_focal_scenes':24,'frozen_digest':frozen,
          'selector_fingerprint':selector_fp,'eligible_for_inference':False})
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start});print({'complete':True,'conditions':len(conditions),'signals':len(signals)},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
