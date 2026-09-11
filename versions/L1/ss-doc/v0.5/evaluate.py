import argparse,time
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,verify
from evaluation.reconfirm_cases import audit_datasets
from evaluation.revision_cases import prepared_data
from evaluation.reconfirm_experiment import episode,probe,failure_regression
from evaluation.oracle import localize,scored
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_revision.learning import learn

def run(out):
    frozen=verify();started=time.perf_counter();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    plan=read(ROOT/'evaluation/PROTOCOL.json');data=read(ROOT/'data/RECONFIRM_DATASETS.json')
    audit=audit_datasets(data,read(ROOT/'data/SPLIT_EXCLUSIONS.json'));write(out/'DATA_AUDIT.json',audit)
    model=PartialModel.load(ROOT/'model');conditions=[];bases=[];signals={}
    for split in plan['data_splits']:
        ds=data['splits'][split];cases=ds['cases'];focal=cases[:12];ordered=[focal[i] for i in ds['query_order']]
        records=prepared_data(model,cases);write(out/f'TEACHERS-{split}.json',records);print({'prepared':split},flush=True)
        for code_i,code in enumerate(plan['code_seeds']):
            for method in plan['memory_methods']:
                base_id=f'd{split}-c{code_i}-{method}';m=RevisionMemory(model.codec.candidates,method,code)
                for r in records:m.register(r['root'],r['targets'],r['kind']=='focal')
                for step in range(5):
                    for r in records[:12]:learn(m,r['teachers'][step]['prepared'])
                for step in range(2):
                    for r in records[12:]:learn(m,r['teachers'][step]['prepared'])
                m.save(out/'base_memories'/base_id);bases.append(base_id)
                baseline=[probe(model,m,c,outputs=False)[0] for c in ordered]
                write(out/'baselines'/(base_id+'.json'),{'memory_fingerprint':m.fingerprint,'probes':baseline,'cost':m.cost()})
                for policy in plan['policies']:
                    for budget in plan['global_teacher_budget_caps']:
                        cid=f'{base_id}-{policy}-b{budget}';current=RevisionMemory.load(out/'base_memories'/base_id,model.codec.candidates)
                        rows=[];used=0
                        for c in ordered:
                            r=episode(model,current,c,policy,budget-used);used+=r['confirmations_used'];rows.append(r)
                        assert used<=budget;fp=current.fingerprint;current.save(out/'memories'/cid)
                        coldmem=RevisionMemory.load(out/'memories'/cid,model.codec.candidates);assert coldmem.fingerprint==fp
                        cold=[]
                        for i,c in enumerate(ordered):
                            row,source,completed=probe(model,coldmem,c);cold.append(row)
                            if i==0:
                                signals[cid+'-initial']=model.vector(source)
                                if completed is not None:signals[cid+'-completed']=model.vector(completed)
                        assert coldmem.fingerprint==fp
                        write(out/'conditions'/(cid+'.json'),{'condition':cid,'base':base_id,'split':split,'code':code,'method':method,'policy':policy,
                              'budget_cap':budget,'actual_confirmations':used,'primary':rows,'cold':cold,'memory_fingerprint':fp,
                              'cost':coldmem.cost(),'eligible_for_inference':False})
                        conditions.append(cid);print({'condition':cid,'asked':used,'correct':sum(r['final']['correct'] for r in rows),
                            'wrong':sum(r['final']['wrong'] for r in rows),'cold_correct':sum(r['correct'] for r in cold)},flush=True)
    write(out/'V04_FAILURE_REGRESSION.json',failure_regression(model))
    regression=[]
    for r in read(ROOT/'data/doc_v01_regression.json'):
        m=r['meaning'];goals=['subject']*len(m['events']);g=model.document.generate(model.document.encode(m),'preserve',goals)
        score=scored(localize(m,m['presentation'],goals),g.get('text'));assert score['semantic_equal'];regression.append({'text':g.get('text'),'score':score})
    write(out/'LANGUAGE_REGRESSION.json',regression);np.savez_compressed(out/'REFERENCE_SIGNALS.npz',**signals)
    write(out/'INDEX.json',{'conditions':conditions,'bases':bases,'main_episodes':len(conditions)*12,'cold_episodes':len(conditions)*12,
          'requested_main_outputs':len(conditions)*24,'requested_cold_outputs':len(conditions)*24,'frozen_digest':frozen,'eligible_for_inference':False})
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-started});print({'complete':True,'conditions':len(conditions),'signals':len(signals)},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
