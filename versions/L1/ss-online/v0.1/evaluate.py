import argparse
import hashlib
import itertools
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
from ss_online.algebra import digest
from ss_online.learning import Learner
from ss_online.model import decisions
from evaluation.cases import stream,validate
from evaluation.integrity import ROOT,verify,write
from evaluation.metrics import probe_metrics,trace_metrics


def feedback(request,label):
    return {'schema':'plm-ss-online-feedback-01','request_id':request['request_id'],'source':'external_teacher','label':label}


def snapshot(learner,case,known,truth,phase,epoch,anchor,arrays):
    rows=[r for group in case['groups'].values() for r in group]
    unknown=[{'id':f'unknown-{i}','context':c} for i,c in enumerate(case['unknown'])]
    all_rows=rows+unknown
    scores=learner.model.scores([r['context'] for r in all_rows]);key=f'p{len(arrays):05d}';arrays[key]=scores
    groups=[]
    for name,start,end in (('A',0,64),('B',64,128),('C',128,192),('never_taught',192,320)):
        groups.append({'group':name,'metrics':probe_metrics(scores[start:end],all_rows[start:end],known,truth)})
    ps=decisions(scores[:64],list('0123'))
    stable={r['id'] for r in case['groups']['A'] if phase!='drift' or r['id'] not in case['changed_A_ids']}
    current={r['id'] for r,p in zip(case['groups']['A'],ps) if p['accepted']==truth[r['id']]}
    anchored=(anchor or set()) & stable
    forgetting={'anchor_defined':anchor is not None,'anchor_correct_count':len(anchored),'lost_anchor_correct':len(anchored-current),
                'stable_A_current_correct':len(current&stable),'stable_A_requests':len(stable)}
    if phase=='drift':
        idx=[i for i,r in enumerate(case['groups']['A']) if r['id'] in case['changed_A_ids']]
        groups.append({'group':'changed_A','metrics':probe_metrics(scores[idx],[case['groups']['A'][i] for i in idx],known,truth)})
        idx=[i for i,r in enumerate(case['groups']['A']) if r['id'] not in case['changed_A_ids']]
        groups.append({'group':'unchanged_A','metrics':probe_metrics(scores[idx],[case['groups']['A'][i] for i in idx],known,truth)})
    return {'phase':phase,'epoch':epoch,'teacher_presentations':learner.step,'known_unique_keys':len(known),
            'scores_array':key,'groups':groups,'forgetting':forgetting,'storage':learner.storage()},current


def run(case,scenario,method,d,code_seed,arrays,out,save):
    learner=Learner.start(method,d,code_seed,'replay-fixed')
    run={'data_seed':case['seed'],'scenario':scenario,'method':method,'dimension':d if method!='exact' else None,'code_seed':code_seed if method!='exact' else 'exact',
         'trace':[],'blocks':[],'snapshots':[],'saved':{},'checks':[]}
    known=set();anchor=None;last_error={}
    truth={r['id']:r['label'] for group in case['groups'].values() for r in group}
    first,_=snapshot(learner,case,known,truth,'initial',0,anchor,arrays);run['snapshots'].append(first)
    start=time.perf_counter();teacher_seconds=0.;probe_seconds=0.
    for block in stream(case,scenario):
        phase=block['phase'];epoch=block['epoch']
        if phase=='drift' and epoch==1:
            for key in case['changed_A_ids']:truth[key]=str((int(truth[key])+1)%4)
            snap,_=snapshot(learner,case,known,truth,'drift',0,anchor,arrays);run['snapshots'].append(snap)
        block_rows=[]
        for event in block['events']:
            assert event['truth']==truth[event['id']]
            tic=time.perf_counter()
            question=learner.question(event['context']);req=question['request']
            new,audit=learner.answer(req,feedback(req,event['teacher_label']))
            teacher_seconds+=time.perf_counter()-tic
            before=audit['before'];after=audit['after']
            previous=last_error.get((event['id'],event['truth']),False)
            row={'step':new.step,'id':event['id'],'phase':phase,'epoch':epoch,'truth':event['truth'],'teacher_label':event['teacher_label'],
                 'seen_before':event['id'] in known,'previous_tentative_error':previous,
                 'before':{k:before[k] for k in ('tentative','accepted')},'after':{k:after[k] for k in ('tentative','accepted')},
                 'updates':audit['updates_this_answer'],'replay_updates':audit['replay_updates'],
                 'teacher_mse_before':audit['teacher_mse_before'],'teacher_mse_after':audit['teacher_mse_after']}
            run['trace'].append(row);block_rows.append(row)
            # Previous-encounter error, measured before that encounter's feedback.
            last_error[(event['id'],event['truth'])]=before['tentative'] is not None and before['tentative']!=event['truth']
            known.add(event['id'])
            assert new.step==learner.step+1 and len(new.buffer)<=32
            assert method=='replay32' or not new.buffer
            assert new.model.metadata['eligible_for_inference'] is False
            learner=new
        run['blocks'].append({'phase':phase,'epoch':epoch,'metrics':trace_metrics(block_rows)})
        tic=time.perf_counter();snap,current=snapshot(learner,case,known,truth,phase,epoch,anchor,arrays)
        if phase=='A' and epoch==4:
            anchor=current
            snap['forgetting']={'anchor_defined':True,'anchor_correct_count':len(anchor),'lost_anchor_correct':0,'stable_A_current_correct':len(anchor),'stable_A_requests':64}
        run['snapshots'].append(snap);probe_seconds+=time.perf_counter()-tic
        if save and ((phase,epoch) in (('A',4),('C',4),('drift',4))):
            name=method+'-'+phase
            learner.save(out/name)
            run['saved'][name]={'step':learner.step,'fingerprint':learner.fingerprint,'model_fingerprint':learner.model.fingerprint}
    run['teacher_sequence_digest']=digest([(r['id'],r['teacher_label']) for r in run['trace']])
    run['checks']=[{'name':'teacher_count','passed':learner.step==896},
                   {'name':'distinct_teacher_keys','passed':len(known)==192},
                   {'name':'feedback_noise_count','passed':sum(r['truth']!=r['teacher_label'] for r in run['trace'])==(8 if scenario=='noisy_first' else 0)},
                   {'name':'replay_capacity','passed':all(s['storage']['replay_entries']<=32 for s in run['snapshots'])},
                   {'name':'only_scripted_external_feedback','passed':[(r['id'],r['teacher_label']) for r in run['trace']]==[(e['id'],e['teacher_label']) for b in stream(case,scenario) for e in b['events']]}]
    run['final_fingerprint']=learner.fingerprint
    return run,{'total_seconds':time.perf_counter()-start,'teacher_transaction_seconds':teacher_seconds,'probe_seconds':probe_seconds}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--development',action='store_true');a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    data=json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))
    cases=data['development' if a.development else 'evaluation'];assert all(validate(c) for c in cases)
    dims=[128] if a.development else protocol['dimensions'];seeds=['phase-dev'] if a.development else protocol['code_seeds']
    result={'experiment':protocol['experiment'],'freeze_hash':'development' if a.development else verify(),'runs':[],'teacher_equality':[],'eligible_for_inference':False}
    performance={'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'runs':[]};arrays={}
    for case,scenario in itertools.product(cases,protocol['scenarios']):
        configs=[(m,d,s) for m,d,s in itertools.product(protocol['methods'],dims,seeds)]+[('exact',128,'exact')]
        seq=None
        for method,d,seed in configs:
            saving=case==cases[0] and scenario=='clean' and d==128 and seed==seeds[0] and method in ('delta','delta5','replay32')
            r,t=run(case,scenario,method,d,seed,arrays,out,saving)
            seq=seq or r['teacher_sequence_digest'];assert seq==r['teacher_sequence_digest']
            result['runs'].append(r);performance['runs'].append(t)
            print('completed',case['seed'],scenario,method,d,seed,'runs',len(result['runs']),flush=True)
        result['teacher_equality'].append({'data_seed':case['seed'],'scenario':scenario,'all_methods_same_teacher_sequence':True,'sequence_digest':seq})
    result['score_arrays']={k:{'shape':list(v.shape),'sha256':hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()} for k,v in arrays.items()}
    result['all_checks_passed']=all(c['passed'] for r in result['runs'] for c in r['checks'])
    assert result['all_checks_passed']
    result['result_digest']=digest(result)
    write(out/'EVALUATION.json',result);write(out/'PERFORMANCE.json',performance);np.savez_compressed(out/'SCORES.npz',**arrays)
    print(json.dumps({'trajectories':len(result['runs']),'feedback_presentations':sum(len(r['trace']) for r in result['runs']),
                      'arrays':len(arrays),'digest':result['result_digest']}),flush=True)


if __name__=='__main__':main()
