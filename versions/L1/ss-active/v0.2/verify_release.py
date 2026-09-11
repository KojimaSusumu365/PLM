"""Recompute all metrics and replay representative training with teacher-free runtime checks."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_multicode.model import Model
from ss_multicode.learning import Learner
from ss_active.selection import diagnostics,normalize_state,select
from ss_active.session import Session,feedback
from evaluation.cases import teaching,truth_map
from evaluation.metrics import probes,summarize,decisions
from evaluation.choose_config import choose
from evaluation.integrity import ROOT,sha,verify,verify_development,write


def command(args,cwd,log,accepted=(0,)):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');env.pop('PYTHONPATH',None)
    p=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',timeout=240)
    with log.open('x',encoding='utf-8') as f:f.write(p.stdout+p.stderr)
    assert p.returncode in accepted,(log.name,p.stderr[-2000:]);return p.stdout,p.stderr


def audit(folder,cases,expected_runs,expected_teachers):
    result=json.loads((folder/'EVALUATION.json').read_text(encoding='utf-8'));original=dict(result);claim=original.pop('result_digest');assert digest(original)==claim and result['all_checks_passed']
    assert len(result['runs'])==expected_runs and result['actual_teacher_presentations']==expected_teachers
    with np.load(folder/'SCORES.npz',allow_pickle=False) as z:
        assert set(z.files)==set(result['arrays']);arrays={k:z[k] for k in z.files}
    for key,v in arrays.items():assert list(v.shape)==result['arrays'][key]['shape'] and hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()==result['arrays'][key]['sha256']
    count=0;revisits=0;world_checks=0;prefix_checks=0
    for r in result['runs']:
        case=cases[r['data_seed'],r['size']];truth=truth_map(case,r['world']);g=r['size'];rows=probes(case);ids=[x['id'] for x in rows];ys=np.array([int(truth.get(k,'-1')) for k in ids])
        base=next(b for b in result['bases'] if (b['data_seed'],b['size'],b['code_seed'])==(r['data_seed'],g,r['code_seed']));controls={int(n):arrays[key] for n,key in base['arrays'].items()}
        ledger={};corrected_at={0:set()};selected_at={0:set()};cfg=r['config'];before=arrays[r['trace_prefix']+'_before'];after=arrays[r['trace_prefix']+'_after']
        assert before.shape==after.shape==(32,4,4) and len(r['trace'])==32
        for i,e in enumerate(r['trace']):
            req=e['request'];sel=req['selection'];key=sel['selected_id'];step=12*g+i+(2*g if i>=16 else 0)
            state=normalize_state({'schema':'plm-ss-active2-selection-state','pool':case['pool'],'ledger':ledger,'strategy':r['strategy'],'seed':r['acquisition_seed'],'config':cfg,'current_step':step})
            assert digest(state)==sel['state_digest'] and sel['index']==i and e['teacher_label']==truth[key]
            q=dict(req);q.pop('request_id');assert digest(q)==req['request_id'];ss=dict(sel);ss.pop('selection_id');assert digest(ss)==sel['selection_id']
            for stage,raw in (('before',before),('after',after)):
                d=decisions(raw[i:i+1]);assert e[stage]=={f:str(int(d[f][0])) if d[f][0]>=0 else None for f in ('tentative','accepted')}
            margin=float(diagnostics(before[i:i+1])['margin'][0]);assert abs(sel['diagnostics']['margin']-margin)<1e-13
            previous=ledger.get(key);assert sel['diagnostics']['previous_visits']==(previous['visits'] if previous else 0)
            if sel['route']=='revisit':
                assert r['strategy'].endswith('_revisit') and i%4==3 and previous and previous['visits']<2
                assert step-previous['last_step']>=cfg['cooldown'] and previous['post_margin']-margin>=cfg['drop_margin'];revisits+=1
            else:assert previous is None
            if sel['route'] in ('random','explore'):
                unseen=[x for x in case['pool'] if x['id'] not in ledger];target=min(unseen,key=lambda x:(digest(['ss-active-order-01',r['acquisition_seed'],x['id']]),x['id']))
                assert key==target['id']
                assert r['strategy']=='random_once' if sel['route']=='random' else r['strategy'].startswith('mixed_') and i%cfg['explore_every']==0
            corrected=set(corrected_at[i])
            if e['before']['tentative'] is not None and e['before']['tentative']!=truth[key] and e['after']['tentative']==truth[key]:corrected.add(key)
            ledger[key]={'visits':1 if previous is None else previous['visits']+1,'last_step':step+1,'post_margin':float(diagnostics(after[i:i+1])['margin'][0])}
            corrected_at[i+1]=corrected;selected_at[i+1]=set(ledger)
        first=corrected_at[16];d_scores=arrays[r['checkpoints'][2]['array']];d_decisions=decisions(d_scores)
        relapse={k for j,k in enumerate(ids) if k in first and d_decisions['tentative'][j]!=ys[j]}
        timeline=[('q4',4,3,0),('q16',16,3,0),('post_D',16,4,2*g),('q20',20,4,2*g),('q32',32,4,2*g),('post_E',32,5,4*g)]
        for s,(name,budget,known,bg) in zip(r['checkpoints'],timeline):
            assert (s['name'],s['acquired'],s['known_groups'],s['background_count'])==(name,budget,known,bg)
            assert s['learner_step']==12*g+budget+bg and s['unique_acquired']==len(selected_at[budget])
            expected=summarize(arrays[s['array']],case,r['world'],known,selected_at[budget],controls[3],controls[known],corrected_at[budget],first if budget>=16 else set(),relapse if known>=4 else set())
            assert s['metrics']==expected;count+=1
        assert r['background_teacher_digest']==digest(teaching(case,'DE',2)) and r['acquisition_teachers']==32 and r['background_teachers']==4*g
        if r['world']=='stationary':
            other=next(s for s in result['runs'] if s['world']=='changed_pool16' and all(s[k]==r[k] for k in ('data_seed','size','code_seed','acquisition_seed','strategy','config_index')))
            assert r['trace'][0]['request']==other['trace'][0]['request'];world_checks+=1
        if r['strategy'] in ('ambiguity_once','mixed_once'):
            other=next(s for s in result['runs'] if s['strategy']==r['strategy'].replace('_once','_revisit') and all(s[k]==r[k] for k in ('data_seed','size','code_seed','acquisition_seed','world','config_index')))
            assert [e['request']['selection']['selected_id'] for e in r['trace'][:16]]==[e['request']['selection']['selected_id'] for e in other['trace'][:16]]
            np.testing.assert_array_equal(before[:16],arrays[other['trace_prefix']+'_before'][:16]);assert r['checkpoints'][1]['model_fingerprint']==other['checkpoints'][1]['model_fingerprint'];prefix_checks+=1
    assert result['two_world_first_requests_equal']==world_checks
    return result,arrays,{'raw_arrays':len(arrays),'checkpoints':count,'world_first_requests':world_checks,'factorial_prefix_checks':prefix_checks,'actual_revisit_teachers':revisits}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=verify();baseline=json.loads((ROOT/'verification/BASELINE.json').read_text(encoding='utf-8'));assert all(sha(ROOT/n)==h for n,h in baseline['copied_files'].items())
    vendor=ROOT/'vendor/PLM-L1-SS-active-v0.1.zip';assert sha(vendor)==baseline['vendor_sha256']
    with zipfile.ZipFile(vendor) as z:
        assert z.testzip() is None;prefix='PLM-L1-SS-active-v0.1/';manifest=json.loads(z.read(prefix+'RELEASE_MANIFEST.json'))['files']
        assert all(hashlib.sha256(z.read(prefix+n)).hexdigest()==h for n,h in manifest.items())
    stdout,stderr=command(['-m','unittest','discover','-s','tests','-v'],ROOT,out/'UNIT_TESTS.log');tests=int(re.search(r'Ran (\d+) tests',stdout+stderr).group(1))
    data=json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'));cases={phase:{(c['seed'],c['size']):c for c in cs} for phase,cs in data.items()}
    dev,dev_arrays,dev_audit=audit(ROOT/'verification/development',cases['development'],80,36352)
    assert dev['freeze_hash']=='development:'+verify_development()
    selected=json.loads((ROOT/'evaluation/SELECTED.json').read_text(encoding='utf-8'));assert selected==choose(dev,json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8')))
    del dev_arrays
    result,arrays,final_audit=audit(ROOT/'results',cases['evaluation'],320,157696);assert result['freeze_hash']==frozen and all(r['config']==selected['config'] for r in result['runs'])
    models={};selection_calls=0;teacher_count=0;replayed_revisits=0
    with tempfile.TemporaryDirectory(prefix='a2verify-') as td:
        temp=Path(td).resolve();trainer=temp/'trainer';runtime=temp/'runtime';trainer.mkdir();runtime.mkdir()
        for package in ('ss_multicode','ss_active'):
            shutil.copytree(ROOT/package,trainer/package,ignore=shutil.ignore_patterns('__pycache__'));(runtime/package).mkdir()
        for n in ('__init__.py','algebra.py','model.py'):shutil.copyfile(ROOT/'ss_multicode'/n,runtime/'ss_multicode'/n)
        for n in ('__init__.py','base_selection.py','selection.py','__main__.py'):shutil.copyfile(ROOT/'ss_active'/n,runtime/'ss_active'/n)
        def compare(name,old,new,case):
            assert old.fingerprint==new.fingerprint;np.testing.assert_array_equal(old.readers,new.readers);np.testing.assert_array_equal(old.checker,new.checker)
            contexts=[r['context'] for r in probes(case)];old.save(runtime/name);write(runtime/'queries.json',contexts)
            stdout,_=command(['-m','ss_active','query','--model',name,'--input','queries.json'],runtime,out/(name+'-QUERY.log'),(0,2));assert json.loads(stdout)==old.predict(contexts);(runtime/'queries.json').unlink()
            models[name]={'contexts':len(contexts),'coefficient_max_difference':0,'fingerprint_equal':True}
        for b in [b for b in result['bases'] if b['saved']]:
            case=cases['evaluation'][b['data_seed'],b['size']];g=case['size']
            write(trainer/'initial.json',{'seed':b['code_seed'],'size':g,'ABC':teaching(case,'ABC',4),'D':teaching(case,'D',2),'E':teaching(case,'E',2)})
            code="import json;from ss_multicode.model import Model;from ss_multicode.learning import Learner,teacher;d=json.load(open('initial.json',encoding='utf-8'));s=Learner(Model('concat512',d['seed']))\nfor group in ('ABC','D','E'):\n for e in d[group]:\n  q=s.question(e['context'])['request'];s=s.answer(q,teacher(q,e['label']))\n name='base-s'+str(d['size']) if group=='ABC' else 'control-s'+str(d['size'])+'-'+group;s.save(name)\nprint(s.fingerprint)"
            command(['-c',code],trainer,out/(f'base-s{g}-TRAIN.log'));(trainer/'initial.json').unlink();teacher_count+=16*g
            for name,fp in b['saved'].items():
                old=Learner.load(ROOT/'results'/name);new=Learner.load(trainer/name);assert old.fingerprint==new.fingerprint==fp;compare(name,old.model,new.model,case)
        for r in [r for r in result['runs'] if r['saved']]:
            case=cases['evaluation'][r['data_seed'],r['size']];stem=f's{case["size"]}-{r["strategy"]}'
            write(trainer/'input.json',{'base':f'base-s{case["size"]}','stem':stem,'pool':case['pool'],'strategy':r['strategy'],'seed':r['acquisition_seed'],'config':r['config'],
                  'responses':[{'id':e['request']['selection']['selected_id'],'label':e['teacher_label']} for e in r['trace']],'D':teaching(case,'D',2),'E':teaching(case,'E',2)})
            code="import json,numpy as np;from ss_multicode.learning import Learner;from ss_active.session import Session,feedback;d=json.load(open('input.json',encoding='utf-8'));s=Session(Learner.load(d['base']),d['pool'],d['strategy'],d['seed'],d['config']);requests=[];before=[];after=[]\nfor group,target in (('D',16),('E',32)):\n while s.acquired<target:\n  q=s.ask();e=d['responses'][s.acquired];assert q['selection']['selected_id']==e['id'];requests.append(q);c=q['selection']['context'];before.append(s.learner.model.raw([c])['readers'][0]);s=s.answer(q,feedback(q,e['label']));after.append(s.learner.model.raw([c])['readers'][0])\n  if s.acquired in (4,16,20,32):s.save(d['stem']+'-q'+str(s.acquired))\n for e in d[group]:\n  q=s.background_question(e['context']);s=s.background_answer(q,feedback(q,e['label']))\n s.save(d['stem']+'-post_'+group)\nnp.savez('trace.npz',before=np.array(before),after=np.array(after));print(json.dumps(requests))"
            stdout,_=command(['-c',code],trainer,out/(stem+'-ACQUISITION.log'));assert json.loads(stdout)==[e['request'] for e in r['trace']]
            with np.load(trainer/'trace.npz',allow_pickle=False) as z:
                for stage in ('before','after'):np.testing.assert_array_equal(z[stage],arrays[r['trace_prefix']+'_'+stage])
            (trainer/'input.json').unlink();(trainer/'trace.npz').unlink();teacher_count+=32+4*case['size'];replayed_revisits+=sum(e['request']['selection']['route']=='revisit' for e in r['trace'])
            for name,meta in r['saved'].items():
                old=Session.load(ROOT/'results'/name);new=Session.load(trainer/name);assert old.fingerprint==new.fingerprint==meta['fingerprint'];compare(name,old.learner.model,new.learner.model,case)
                write(runtime/'state.json',old.selection_state)
                stdout,_=command(['-m','ss_active','select','--model',name,'--state','state.json'],runtime,out/(name+'-SELECT.log'));assert json.loads(stdout)==old.ask()['selection'];(runtime/'state.json').unlink();selection_calls+=1
        command(['-c',"from pathlib import Path;import sys;from ss_active.selection import select;assert not Path('ss_active/session.py').exists();assert not Path('ss_multicode/learning.py').exists();assert not Path('data').exists();assert not Path('evaluation').exists();assert not list(Path('.').rglob('learner.json'));assert not list(Path('.').rglob('session.json'));assert 'ss_multicode.learning' not in sys.modules;assert 'ss_active.session' not in sys.modules;print('Model and unlabeled scalar ledger only; no teachers or evaluation truth')"],runtime,out/'RUNTIME_BOUNDARY.log')
        name='s128-mixed_revisit-post_D';s=Session.load(ROOT/'results'/name);q=s.ask();case=cases['evaluation']['active2-final-0',128];fb=feedback(q,truth_map(case,'stationary')[q['selection']['selected_id']]);expected=s.answer(q,fb)
        write(trainer/'request.json',q);write(trainer/'feedback.json',fb)
        command(['-m','ss_active','teach','--session',name,'--request','request.json','--feedback','feedback.json','--out','resumed'],trainer,out/'RESUME.log');assert Session.load(trainer/'resumed').fingerprint==expected.fingerprint
        command(['-m','ss_active','teach','--session','resumed','--request','request.json','--feedback','feedback.json','--out','stale-output'],trainer,out/'STALE.log',(2,));assert not (trainer/'stale-output').exists()
        (trainer/'feedback.json').unlink();write(trainer/'feedback.json',fb|{'source':'model_prediction'})
        command(['-m','ss_active','teach','--session',name,'--request','request.json','--feedback','feedback.json','--out','pseudo-output'],trainer,out/'PSEUDO.log',(2,));assert not (trainer/'pseudo-output').exists()
    manifest_count=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        manifest=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files'];actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='RELEASE_MANIFEST.json'};assert actual==manifest;manifest_count=len(actual)
    report={'status':'passed','unit_tests':tests,'freeze_hash':frozen,'result_digest':result['result_digest'],'development':dev_audit,'final':final_audit,
            'development_choice_recomputed':True,'isolated_teacher_presentations':teacher_count,'models':models,'isolated_selection_calls':selection_calls,
            'isolated_revisit_teachers':replayed_revisits,'prediction_and_selection_without_teachers':True,'cli_resume_matches':True,
            'stale_and_pseudo_feedback_rejected_without_output':True,'manifest_files':manifest_count,'all320_trajectories_retrained_here':False,
            'linux_tested':False,'p1_s1_integrated':False,'eligible_for_inference':False}
    write(out/'VERIFICATION.json',report);print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
