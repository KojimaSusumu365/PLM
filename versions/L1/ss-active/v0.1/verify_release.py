"""Recompute metrics, replay isolated acquisitions, and test teacher-free runtime boundaries."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import numpy as np
from ss_multicode.algebra import digest
from ss_multicode.model import Model
from ss_multicode.learning import Learner
from ss_active.session import Session, feedback
from ss_active.selection import select
from evaluation.cases import teaching, truth_map
from evaluation.metrics import summarize, probe_context
from evaluation.integrity import ROOT, sha, verify, write


def command(args, cwd, log, accepted=(0,)):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1'); env.pop('PYTHONPATH',None)
    p=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,text=True,encoding='utf-8',capture_output=True,timeout=180)
    with log.open('x',encoding='utf-8') as f: f.write(p.stdout+p.stderr)
    assert p.returncode in accepted,(log.name,p.stderr[-2000:])
    return p.stdout,p.stderr


def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); a=p.parse_args(); out=Path(a.out).resolve(); out.mkdir(parents=True,exist_ok=False)
    frozen=verify(); baseline=json.loads((ROOT/'verification/BASELINE.json').read_text(encoding='utf-8'))
    assert all(sha(ROOT/n)==h for n,h in baseline['copied_core_files'].items())
    vendor=ROOT/'vendor/PLM-L1-SS-multicode-v0.1.zip'; assert sha(vendor)==baseline['vendor_sha256']
    with zipfile.ZipFile(vendor) as z:
        assert z.testzip() is None; prefix='PLM-L1-SS-multicode-v0.1/'
        old=json.loads(z.read(prefix+'RELEASE_MANIFEST.json'))['files']
        assert all(hashlib.sha256(z.read(prefix+n)).hexdigest()==h for n,h in old.items())
    stdout,stderr=command(['-m','unittest','discover','-s','tests','-v'],ROOT,out/'UNIT_TESTS.log')
    tests=int(re.search(r'Ran (\d+) tests',stdout+stderr).group(1))
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8')); claimed=result.pop('result_digest')
    assert digest(result)==claimed and result['freeze_hash']==frozen and result['all_checks_passed']
    assert len(result['runs'])==192 and result['actual_teacher_presentations']==172032
    cases={(c['seed'],c['size']):c for c in json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
    with np.load(ROOT/'results/SCORES.npz',allow_pickle=False) as z:
        assert set(z.files)==set(result['arrays']); arrays={k:z[k] for k in z.files}
    for k,v in arrays.items():
        meta=result['arrays'][k]; assert list(v.shape)==meta['shape'] and hashlib.sha256(v.astype('<f8').tobytes()).hexdigest()==meta['sha256']
    snapshots=0; two_worlds=0
    for run in result['runs']:
        case=cases[run['data_seed'],run['size']]; truth=truth_map(case,run['scenario']); base=arrays[run['checkpoints'][0]['array']]
        selected=[]; corrected=[]
        assert len(run['trace'])==32 and run['acquired_ids']==[r['request']['selection']['selected_id'] for r in run['trace']]
        from ss_multicode.model import decide,policy
        for i,row in enumerate(run['trace']):
            req=row['request']; key=req['selection']['selected_id']; assert key not in selected; selected.append(key)
            assert row['teacher_label']==row['truth']==truth[key]
            for stage in ('before','after'):
                raw=arrays[run['trace_prefix']+'_'+stage][i:i+1]; ds=decide({'readers':raw,'checker':np.empty((1,0))},policy())
                assert row[stage]=={f:str(int(ds[f][0])) if ds[f][0]>=0 else None for f in ('tentative','accepted')}
            if row['before']['tentative'] is not None and row['before']['tentative']!=row['truth'] and row['after']['tentative']==row['truth']: corrected.append((i+1,key))
            q=dict(req); q.pop('request_id'); assert digest(q)==req['request_id']
            sel=dict(req['selection']); sid=sel.pop('selection_id'); assert digest(sel)==sid
        assert set(selected)<={r['id'] for r in case['pool']}
        for pre,post in zip(run['checkpoints'][::2],run['checkpoints'][1::2]):
            b=pre['budget']; assert b==post['budget']; correction_ids=[k for n,k in corrected if n<=b]
            ps=arrays[pre['array']]
            for snap,is_post in ((pre,False),(post,True)):
                scores=arrays[snap['array']]
                assert summarize(scores,case,run['scenario'],selected[:b],is_post,base,ps,correction_ids)==snap['metrics']
                assert snap['learner_step']==12*case['size']+b+(2*case['size'] if is_post else 0)
                snapshots+=1
        if run['scenario']=='stationary':
            other=next(r for r in result['runs'] if r['scenario']=='changed_pool16' and all(r[k]==run[k] for k in ('data_seed','size','code_seed','acquisition_seed','strategy')))
            assert run['trace'][0]['request']==other['trace'][0]['request']; two_worlds+=1
    comparisons={}; selected_calls=0; teacher_count=0
    with tempfile.TemporaryDirectory(prefix='asverify-') as temp:
        basepath=Path(temp).resolve(); trainer=basepath/'trainer'; runtime=basepath/'runtime'; trainer.mkdir(); runtime.mkdir()
        for package in ('ss_multicode','ss_active'):
            shutil.copytree(ROOT/package,trainer/package,ignore=shutil.ignore_patterns('__pycache__'))
            (runtime/package).mkdir()
        for n in ('__init__.py','algebra.py','model.py'): shutil.copyfile(ROOT/'ss_multicode'/n,runtime/'ss_multicode'/n)
        for n in ('__init__.py','selection.py','__main__.py'): shutil.copyfile(ROOT/'ss_active'/n,runtime/'ss_active'/n)
        def compare_model(name,original,fresh,case):
            assert original.fingerprint==fresh.fingerprint
            np.testing.assert_array_equal(original.readers,fresh.readers); np.testing.assert_array_equal(original.checker,fresh.checker)
            contexts=[r['context'] for r in probe_context(case)]
            original.save(runtime/name); write(runtime/'queries.json',contexts)
            stdout,_=command(['-m','ss_active','query','--model',name,'--input','queries.json'],runtime,out/(name+'-QUERY.log'),(0,2))
            assert json.loads(stdout)==original.predict(contexts); (runtime/'queries.json').unlink()
            comparisons[name]={'contexts':len(contexts),'coefficient_max_difference':0,'fingerprint_equal':True}
        for b in [b for b in result['bases'] if 'saved' in b]:
            case=cases[b['data_seed'],b['size']]; initial=teaching(case,'ABC',4)
            write(trainer/'initial.json',{'seed':b['code_seed'],'name':b['saved'],'teaching':[{'context':e['context'],'label':e['label']} for e in initial]})
            code="import json;from ss_multicode.model import Model;from ss_multicode.learning import Learner,teacher;d=json.load(open('initial.json',encoding='utf-8'));s=Learner(Model('concat512',d['seed']))\nfor e in d['teaching']:\n q=s.question(e['context'])['request'];s=s.answer(q,teacher(q,e['label']))\ns.save(d['name']);print(s.fingerprint)"
            command(['-c',code],trainer,out/(b['saved']+'-TRAIN.log')); (trainer/'initial.json').unlink(); teacher_count+=len(initial)
            old= Learner.load(ROOT/'results'/b['saved']); new=Learner.load(trainer/b['saved']); assert old.fingerprint==new.fingerprint==b['fingerprint']
            compare_model(b['saved'],old.model,new.model,case)
        for run in [r for r in result['runs'] if r['saved']]:
            case=cases[run['data_seed'],run['size']]; stem=f's{case["size"]}-{run["strategy"]}'
            desc={'base':f'base-s{case["size"]}','stem':stem,'pool':case['pool'],'strategy':run['strategy'],'seed':run['acquisition_seed'],
                  'responses':[{'id':row['request']['selection']['selected_id'],'label':row['teacher_label']} for row in run['trace']],
                  'challenge':[{'context':e['context'],'label':e['label']} for e in teaching(case,'D',2)]}
            write(trainer/'input.json',desc)
            code="import json,numpy as np;from ss_multicode.learning import Learner,teacher;from ss_active.session import Session,feedback;d=json.load(open('input.json',encoding='utf-8'));s=Session(Learner.load(d['base']),d['pool'],d['strategy'],d['seed']);requests=[];before=[];after=[]\nfor b in (0,4,16,32):\n while len(s.acquired)<b:\n  q=s.ask();e=d['responses'][len(s.acquired)];assert q['selection']['selected_id']==e['id'];requests.append(q);c=q['selection']['context'];before.append(s.learner.model.raw([c])['readers'][0]);s=s.answer(q,feedback(q,e['label']));after.append(s.learner.model.raw([c])['readers'][0])\n s.save(d['stem']+'-b'+str(b));post=s.learner\n for e in d['challenge']:\n  q=post.question(e['context'])['request'];post=post.answer(q,teacher(q,e['label']))\n post.save(d['stem']+'-b'+str(b)+'-post')\nnp.savez('trace.npz',before=np.array(before),after=np.array(after));print(json.dumps(requests))"
            stdout,_=command(['-c',code],trainer,out/(stem+'-ACQUISITION.log'))
            assert json.loads(stdout)==[r['request'] for r in run['trace']]
            with np.load(trainer/'trace.npz',allow_pickle=False) as z:
                for stage in ('before','after'): np.testing.assert_array_equal(z[stage],arrays[run['trace_prefix']+'_'+stage])
            (trainer/'input.json').unlink(); (trainer/'trace.npz').unlink(); teacher_count+=32+4*2*case['size']
            for name,meta in run['saved'].items():
                if meta['kind']=='session':
                    original=Session.load(ROOT/'results'/name); fresh=Session.load(trainer/name)
                    assert original.fingerprint==fresh.fingerprint==meta['fingerprint']
                    om=original.learner.model; fm=fresh.learner.model
                    compare_model(name,om,fm,case)
                    write(runtime/'pool.json',original.pool)
                    stdout,_=command(['-m','ss_active','select','--model',name,'--pool','pool.json','--strategy',original.strategy,'--seed',original.seed,'--index',str(len(original.acquired))],runtime,out/(name+'-SELECT.log'))
                    assert json.loads(stdout)==original.ask()['selection']; (runtime/'pool.json').unlink(); selected_calls+=1
                else:
                    original=Learner.load(ROOT/'results'/name); fresh=Learner.load(trainer/name)
                    assert original.fingerprint==fresh.fingerprint==meta['fingerprint']; compare_model(name,original.model,fresh.model,case)
        command(['-c',"from pathlib import Path;import sys;from ss_active.selection import select;assert not Path('ss_active/session.py').exists();assert not Path('ss_multicode/learning.py').exists();assert not Path('data').exists();assert not Path('evaluation').exists();assert not list(Path('.').rglob('session.json'));assert not list(Path('.').rglob('learner.json'));assert 'ss_active.session' not in sys.modules;assert 'ss_multicode.learning' not in sys.modules;print('Prediction/selection runtime has no learner, teacher responses, evaluation truth or session ledger')"],runtime,out/'RUNTIME_BOUNDARY.log')
        name='s128-disagreement-b0'; s=Session.load(ROOT/'results'/name); req=s.ask()
        case=cases['active-final-0',128]; fb=feedback(req,truth_map(case,'stationary')[req['selection']['selected_id']]); expected=s.answer(req,fb)
        write(trainer/'request.json',req); write(trainer/'feedback.json',fb)
        command(['-m','ss_active','teach','--session',name,'--request','request.json','--feedback','feedback.json','--out','resumed'],trainer,out/'RESUME.log')
        assert Session.load(trainer/'resumed').fingerprint==expected.fingerprint
        command(['-m','ss_active','teach','--session','resumed','--request','request.json','--feedback','feedback.json','--out','stale-output'],trainer,out/'STALE.log',(2,)); assert not (trainer/'stale-output').exists()
        (trainer/'feedback.json').unlink(); write(trainer/'feedback.json',dict(fb,source='model_prediction'))
        command(['-m','ss_active','teach','--session',name,'--request','request.json','--feedback','feedback.json','--out','pseudo-output'],trainer,out/'PSEUDO.log',(2,)); assert not (trainer/'pseudo-output').exists()
    manifest_count=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        manifest=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files']
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='RELEASE_MANIFEST.json'}
        assert actual==manifest; manifest_count=len(actual)
    report={'status':'passed','unit_tests':tests,'freeze_hash':frozen,'result_digest':claimed,'raw_arrays_rechecked':len(arrays),
            'checkpoints_rechecked':snapshots,'two_world_first_request_checks':two_worlds,'isolated_teacher_presentations':teacher_count,
            'models':comparisons,'isolated_selection_calls':selected_calls,'prediction_and_selection_without_teachers':True,
            'cli_resume_matches':True,'stale_and_pseudo_feedback_rejected_without_output':True,'manifest_files':manifest_count,
            'all192_trajectories_retrained_here':False,'linux_tested':False,'p1_s1_integrated':False,'eligible_for_inference':False}
    write(out/'VERIFICATION.json',report); print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
