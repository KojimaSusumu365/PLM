import argparse,hashlib,itertools,json,platform,sys,time
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest,canonical
from ss_multicode.model import Model,policy
from ss_multicode.learning import Learner,teacher
from ss_active.session import Session,feedback
from evaluation.cases import teaching,truth_map,validate
from evaluation.metrics import probes,summarize,decisions
from evaluation.integrity import ROOT,verify,verify_development,write


def teach_events(learner,events):
    for e in events:
        q=learner.question(e['context'])['request'];learner=learner.answer(q,teacher(q,e['label']))
    return learner


def run(base,case,world,strategy,seed,config,config_index,controls,arrays,out,save):
    base_at_start=base.fingerprint
    s=Session(base,case['pool'],strategy,seed,config);truth=truth_map(case,world);rows=probes(case);contexts=[r['context'] for r in rows]
    ids=[r['id'] for r in rows];truth_values=np.array([int(truth.get(k,'-1')) for k in ids])
    trace=[];snaps=[];corrected=set();first_corrected=set();post_d_relapsed=set();saved={};raw_before=[];raw_after=[]
    times={'selection_seconds':0.,'response_seconds_including_revalidation':0.,'background_seconds':0.}
    logical=0;routes={};stem=f's{case["size"]}-{strategy}'
    def checkpoint(name,known_groups):
        scores=s.learner.model.raw(contexts)['readers'];key=f'p{len(arrays):05d}';arrays[key]=scores
        snap={'name':name,'array':key,'acquired':s.acquired,'unique_acquired':len(s.selection_state['ledger']),
              'learner_step':s.learner.step,'background_count':s.background_count,'known_groups':known_groups,
              'model_fingerprint':s.learner.model.fingerprint,'session_fingerprint':s.fingerprint,
              'metrics':summarize(scores,case,world,known_groups,s.selection_state['ledger'],controls[3],controls[known_groups],corrected,first_corrected,post_d_relapsed),
              'resources':s.learner.storage()|{'selection_state_json_bytes':len(canonical(s.selection_state).encode('utf-8')),
                  'ledger_entries':len(s.selection_state['ledger']),'logical_selection_contexts_scored':logical,'route_counts':dict(routes)}}
        snaps.append(snap)
        if save:
            filename=stem+'-'+name;s.save(out/filename);saved[filename]={'name':name,'fingerprint':s.fingerprint}
    for block in (1,2):
        while s.acquired<16*block:
            tic=time.perf_counter();req=s.ask();times['selection_seconds']+=time.perf_counter()-tic
            selected=req['selection'];key=selected['selected_id'];context=selected['context'];label=truth[key]
            before=s.learner.model.predict([context])[0];rb=s.learner.model.raw([context])['readers'][0]
            tic=time.perf_counter();new=s.answer(req,feedback(req,label));times['response_seconds_including_revalidation']+=time.perf_counter()-tic
            after=new.learner.model.predict([context])[0];ra=new.learner.model.raw([context])['readers'][0]
            if before['tentative'] is not None and before['tentative']!=label and after['tentative']==label:corrected.add(key)
            trace.append({'request':req,'teacher_label':label,'before':{k:before[k] for k in ('tentative','accepted')},
                          'after':{k:after[k] for k in ('tentative','accepted')},'next_session_fingerprint':new.fingerprint})
            raw_before.append(rb);raw_after.append(ra);logical+=selected['diagnostics']['contexts_scored_this_call'];routes[selected['route']]=routes.get(selected['route'],0)+1;s=new
            if s.acquired==16:first_corrected=set(corrected)
            if s.acquired in (4,16,20,32):checkpoint('q'+str(s.acquired),3 if block==1 else 4)
        group='D' if block==1 else 'E';tic=time.perf_counter()
        for e in teaching(case,group,2):
            q=s.background_question(e['context']);s=s.background_answer(q,feedback(q,e['label']))
        times['background_seconds']+=time.perf_counter()-tic
        if group=='D':
            ds=decisions(s.learner.model.raw(contexts)['readers'])
            post_d_relapsed={key for i,key in enumerate(ids) if key in first_corrected and ds['tentative'][i]!=truth_values[i]}
        checkpoint('post_'+group,4 if group=='D' else 5)
    prefix=f't{len(arrays):05d}';arrays[prefix+'_before']=np.array(raw_before);arrays[prefix+'_after']=np.array(raw_after)
    assert s.acquired==32 and s.background_count==4*case['size'] and s.learner.step==base.step+32+4*case['size']
    assert routes.get('revisit',0)<=4
    if strategy.endswith('_once'):assert len(s.selection_state['ledger'])==32
    result={'data_seed':case['seed'],'size':case['size'],'code_seed':base.model.seed,'world':world,'strategy':strategy,'acquisition_seed':seed,
            'config':config,'config_index':config_index,'base_fingerprint':base.fingerprint,'pool_digest':digest(case['pool']),
            'trace':trace,'trace_prefix':prefix,'checkpoints':snaps,'saved':saved,'final_session_fingerprint':s.fingerprint,
            'acquisition_teachers':32,'background_teachers':s.background_count,'background_teacher_digest':digest(teaching(case,'DE',2)),
            'checks':{'budget_accounting':True,'once_or_max2_visits':all(e['visits']<=2 for e in s.selection_state['ledger'].values()),
                      'pool_only':set(s.selection_state['ledger'])<={r['id'] for r in case['pool']},'base_immutable':base.fingerprint==base_at_start},
            'eligible_for_inference':False}
    return result,times


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--development',action='store_true');a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'));data=json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['development' if a.development else 'evaluation']
    if a.development:
        code_seeds=['active2-code-dev'];acq_seeds=['active2-acq-dev'];configs=list(enumerate(protocol['configuration_grid']));frozen='development:'+verify_development()
    else:
        selected=json.loads((ROOT/'evaluation/SELECTED.json').read_text(encoding='utf-8'));configs=[(selected['config_index'],selected['config'])];code_seeds=protocol['code_seeds'];acq_seeds=protocol['acquisition_seeds'];frozen=verify()
    result={'experiment':protocol['experiment'],'freeze_hash':frozen,'bases':[],'runs':[],'eligible_for_inference':False};arrays={}
    perf={'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'base_seconds':[],'control_seconds':[],'runs':[]}
    for case,code in itertools.product(data,code_seeds):
        assert validate(case);contexts=[r['context'] for r in probes(case)];initial=teaching(case,'ABC',4);tic=time.perf_counter();base=teach_events(Learner(Model('concat512',code,acceptance=policy())),initial);perf['base_seconds'].append(time.perf_counter()-tic)
        before=base.fingerprint;tic=time.perf_counter();ctrl_d=teach_events(base,teaching(case,'D',2));ctrl_e=teach_events(ctrl_d,teaching(case,'E',2));perf['control_seconds'].append(time.perf_counter()-tic);assert base.fingerprint==before
        controls={3:base.model.raw(contexts)['readers'],4:ctrl_d.model.raw(contexts)['readers'],5:ctrl_e.model.raw(contexts)['readers']};keys={}
        for n,v in controls.items():key=f'b{len(arrays):05d}';arrays[key]=v;keys[str(n)]=key
        descriptor={'data_seed':case['seed'],'size':case['size'],'code_seed':code,'fingerprint':base.fingerprint,'teachers':len(initial),
                    'control_teachers':4*case['size'],'arrays':keys,'teacher_digest':digest(initial),'saved':{}}
        save=case['seed']==data[0]['seed'] and code==code_seeds[0]
        if save:
            for name,learner in ((f'base-s{case["size"]}',base),(f'control-s{case["size"]}-D',ctrl_d),(f'control-s{case["size"]}-E',ctrl_e)):
                learner.save(out/name);descriptor['saved'][name]=learner.fingerprint
        result['bases'].append(descriptor)
        for (ci,cfg),world,acq,strategy in itertools.product(configs,protocol['worlds'],acq_seeds,protocol['strategies']):
            r,t=run(base,case,world,strategy,acq,cfg,ci,controls,arrays,out,save and ci==configs[0][0] and world=='stationary' and acq==acq_seeds[0]);assert base.fingerprint==before
            result['runs'].append(r);perf['runs'].append(t);print('completed',len(result['runs']),case['seed'],case['size'],world,strategy,ci,flush=True)
    checks=[]
    for r in [r for r in result['runs'] if r['world']=='stationary']:
        other=next(s for s in result['runs'] if s['world']=='changed_pool16' and all(s[k]==r[k] for k in ('data_seed','size','code_seed','acquisition_seed','strategy','config_index')))
        assert r['trace'][0]['request']==other['trace'][0]['request'];checks.append(True)
    result['two_world_first_requests_equal']=len(checks);result['arrays']={k:{'shape':list(v.shape),'sha256':hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()} for k,v in arrays.items()}
    result['actual_teacher_presentations']=sum(b['teachers']+b['control_teachers'] for b in result['bases'])+sum(r['acquisition_teachers']+r['background_teachers'] for r in result['runs'])
    assert len(result['runs'])==(80 if a.development else 320) and result['actual_teacher_presentations']==(36352 if a.development else 157696)
    result['all_checks_passed']=all(all(r['checks'].values()) for r in result['runs']);assert result['all_checks_passed'];result['result_digest']=digest(result)
    write(out/'EVALUATION.json',result);write(out/'PERFORMANCE.json',perf);np.savez_compressed(out/'SCORES.npz',**arrays)
    print(json.dumps({'runs':len(result['runs']),'teachers':result['actual_teacher_presentations'],'arrays':len(arrays),'digest':result['result_digest']}),flush=True)


if __name__=='__main__':main()
