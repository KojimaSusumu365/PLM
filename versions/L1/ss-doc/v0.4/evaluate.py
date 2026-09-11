import argparse,copy,time
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,verify
from evaluation.revision_cases import cases,prepared_data,fresh
from evaluation.revision_experiment import query
from evaluation.oracle import localize,scored
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_revision.learning import learn,request,teach
from ss_revision.runtime import complete

def run(out):
    frozen=verify();start=time.perf_counter();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    plan=read(ROOT/'evaluation/PROTOCOL.json');model=PartialModel.load(ROOT/'model');signals={};index=[]
    for seed in plan['data_seeds']:
        data=cases(seed);records=prepared_data(model,data);write(out/f'DATA-{seed}.json',data);write(out/f'TEACHERS-{seed}.json',records)
        focal=data[:24];fr=records[:24]
        print({'prepared_data':seed},flush=True)
        for code_i,code in enumerate(plan['code_seeds']):
            for load in plan['background_loads']:
                for method in plan['methods']:
                    cid=f'd{seed}-c{code_i}-b{load}-{method}';m=RevisionMemory(model.codec.candidates,method,code)
                    for r in records[:24+load]:m.register(r['root'],r['targets'],r['kind']=='focal')
                    checkpoints=[]
                    for step in range(5):
                        for r in fr:learn(m,r['teachers'][step]['prepared'])
                        checkpoints.extend(query(model,m,c,step,outputs=False) for c in focal[:2])
                    m.save(out/'before_background'/cid)
                    protected=m.ss.parts['protected'].weights.copy() if 'protected' in m.ss.parts else None
                    for step in range(2):
                        for r in records[24:24+load]:learn(m,r['teachers'][step]['prepared'])
                    protected_equal=None if protected is None else bool(np.array_equal(protected,m.ss.parts['protected'].weights))
                    fp=m.fingerprint;m.save(out/'memories'/cid);m=RevisionMemory.load(out/'memories'/cid,model.codec.candidates);assert fp==m.fingerprint
                    primary=[query(model,m,c,mode=('missing','ambiguous','mixed')[i%3]) for i,c in enumerate(focal)]
                    controls={mode:[query(model,m,c,mode=mode) for c in focal[:6]] for mode in ('only_a','only_b','other_episode','changed_fixed','conflict','explicit_old')}
                    rejections=[]
                    for c,r in zip(focal[:6],fr[:6]):
                        p=model.encode(c['final']);t=c['scope']['mutable'][0]
                        for kind in ('old_rebound','future_gap','duplicate_current'):
                            msg=request(model,m,c['scope'],p,t,c['history_values'][t][1],'revise')
                            if kind=='old_rebound':msg.update(base_revision=0,revision=1)
                            elif kind=='future_gap':msg['revision']+=1
                            else:msg['base_revision']-=1;msg['revision']-=1
                            before=m.fingerprint
                            try:teach(model,m,c['scope'],p,msg);reason=None
                            except ValueError as e:reason=str(e)
                            assert reason=='stale_or_out_of_order_confirmation' and before==m.fingerprint
                            rejections.append({'case_id':c['id'],'kind':kind,'reason':reason,'memory_unchanged':True})
                    packet=model.encode(fresh(focal[0]));signals[cid+'-initial']=model.vector(packet)
                    done=complete(model,m,focal[0]['scope'],packet)
                    if 'packet' in done:signals[cid+'-completed']=model.vector(done['packet'])
                    result={'condition':cid,'method':method,'data_seed':seed,'code_seed':code,'background_episodes':load,
                            'focal_confirmations':120,'background_confirmations':load*2,'memory_fingerprint':fp,
                            'checkpoints':checkpoints,'primary':primary,'controls':controls,'rejected_confirmations':rejections,
                            'protected_unchanged_during_background':protected_equal,'cost':m.cost(),'eligible_for_inference':False}
                    write(out/'conditions'/(cid+'.json'),result);index.append(cid)
                    print({'condition':cid,'correct':sum(q['correct'] for q in primary),'wrong':sum(q['wrong'] for q in primary),'held':sum(q['status']!='completed' for q in primary)},flush=True)
    regression=[]
    for r in read(ROOT/'data/doc_v01_regression.json'):
        m=r['meaning'];expected=localize(m,m['presentation'],['subject']*len(m['events']))
        g=model.document.generate(model.document.encode(m),'preserve',['subject']*len(m['events']))
        regression.append({'text':g.get('text'),'score':scored(expected,g.get('text'))})
    assert all(r['score']['semantic_equal'] for r in regression)
    write(out/'REGRESSION.json',regression);np.savez_compressed(out/'REFERENCE_SIGNALS.npz',**signals)
    write(out/'INDEX.json',{'conditions':index,'primary_queries':len(index)*24,'requested_outputs':len(index)*48,
                          'frozen_digest':frozen,'eligible_for_inference':False})
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start})
    print({'complete':True,'conditions':len(index),'reference_arrays':len(signals)},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
