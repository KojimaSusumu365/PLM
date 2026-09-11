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
from ss_online.algebra import digest
from ss_online.model import Model,decisions
from ss_online.learning import Learner
from evaluation.cases import stream
from evaluation.integrity import ROOT,sha,verify,write
from evaluation.metrics import probe_metrics,trace_metrics
from evaluate import feedback


def command(args,cwd,log,accepted=(0,)):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');env.pop('PYTHONPATH',None)
    p=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,text=True,encoding='utf-8',capture_output=True,timeout=180)
    with log.open('x',encoding='utf-8') as f:f.write(p.stdout+p.stderr)
    if p.returncode not in accepted:raise ValueError(f'{log.name}: {p.stderr[-1500:]}')
    return p.stdout,p.stderr


def recheck(result,case_map,arrays):
    total=0
    for run in result['runs']:
        case=case_map[run['data_seed']];events=[e for b in stream(case,run['scenario']) for e in b['events']]
        assert len(events)==len(run['trace'])==896
        known=set();last={}
        for i,(event,row) in enumerate(zip(events,run['trace'])):
            assert row['step']==i+1 and all(row[k]==event[k] for k in ('id','truth','teacher_label'))
            assert row['seen_before']==(row['id'] in known)
            assert row['previous_tentative_error']==last.get((row['id'],row['truth']),False)
            known.add(row['id']);last[row['id'],row['truth']]=row['before']['tentative'] is not None and row['before']['tentative']!=row['truth']
        assert run['teacher_sequence_digest']==digest([(r['id'],r['teacher_label']) for r in run['trace']])
        for block in run['blocks']:
            rows=[r for r in run['trace'] if r['phase']==block['phase'] and r['epoch']==block['epoch']]
            assert trace_metrics(rows)==block['metrics']
        anchors=set()
        for snap in run['snapshots']:
            phase=snap['phase'];rows=[r for g in case['groups'].values() for r in g]
            unknown=[{'id':f'unknown-{i}','context':c} for i,c in enumerate(case['unknown'])]
            known={r['id'] for r in run['trace'][:snap['teacher_presentations']]}
            truth={r['id']:r['label'] for r in rows}
            if phase=='drift':
                for key in case['changed_A_ids']:truth[key]=str((int(truth[key])+1)%4)
            scores=arrays[snap['scores_array']]
            for group in snap['groups']:
                g=group['group']
                if g in ('A','B','C'):
                    start={'A':0,'B':64,'C':128}[g];rs=rows[start:start+64];ss=scores[start:start+64]
                elif g=='never_taught':rs=unknown;ss=scores[192:]
                else:
                    idx=[i for i,r in enumerate(case['groups']['A']) if (r['id'] in case['changed_A_ids'])==(g=='changed_A')]
                    rs=[rows[i] for i in idx];ss=scores[idx]
                assert probe_metrics(ss,rs,known,truth)==group['metrics']
            preds=decisions(scores[:64],list('0123'));correct={r['id'] for r,p in zip(case['groups']['A'],preds) if p['accepted']==truth[r['id']]}
            if phase=='A' and snap['epoch']==4:anchors=correct
            stable={r['id'] for r in case['groups']['A'] if phase!='drift' or r['id'] not in case['changed_A_ids']}
            assert snap['forgetting']['anchor_correct_count']==len(anchors&stable)
            assert snap['forgetting']['lost_anchor_correct']==len((anchors&stable)-correct)
            total+=1
    return total


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=verify();baseline=json.loads((ROOT/'verification/BASELINE.json').read_text(encoding='utf-8'))
    assert all(sha(ROOT/n)==h for n,h in baseline['copied_files'].items())
    vendor=ROOT/'vendor/PLM-L1-SS-weighting-v0.1.zip'
    assert sha(vendor)=='74603cf710373c0cc34cba8f52f8db2ffb00352f5672483481778fc6e4306525'
    with zipfile.ZipFile(vendor) as z:
        assert z.testzip() is None;prefix='PLM-L1-SS-weighting-v0.1/'
        old=json.loads(z.read(prefix+'RELEASE_MANIFEST.json'))['files']
        assert all(hashlib.sha256(z.read(prefix+n)).hexdigest()==h for n,h in old.items())
    stdout,stderr=command(['-m','unittest','discover','-s','tests','-v'],ROOT,out/'UNIT_TESTS.log')
    tests=int(re.search(r'Ran (\d+) tests',stdout+stderr).group(1))
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'));claimed=result.pop('result_digest')
    assert digest(result)==claimed and result['freeze_hash']==frozen and result['all_checks_passed']
    cases={c['seed']:c for c in json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
    with np.load(ROOT/'results/SCORES.npz',allow_pickle=False) as z:
        assert set(z.files)==set(result['score_arrays'])
        arrays={k:z[k] for k in z.files}
        for k,meta in result['score_arrays'].items():assert list(arrays[k].shape)==meta['shape'] and hashlib.sha256(arrays[k].astype('<f8').tobytes()).hexdigest()==meta['sha256']
        probes=recheck(result,cases,arrays)
    comparisons={};replayed=0
    with tempfile.TemporaryDirectory(prefix='sover-') as temp:
        base=Path(temp).resolve();trainer=base/'trainer';trainer.mkdir();runtime=base/'runtime';runtime.mkdir()
        shutil.copytree(ROOT/'ss_online',trainer/'ss_online',ignore=shutil.ignore_patterns('__pycache__'))
        (runtime/'ss_online').mkdir()
        for n in ('__init__.py','algebra.py','model.py','__main__.py'):shutil.copyfile(ROOT/'ss_online'/n,runtime/'ss_online'/n)
        for run in [r for r in result['runs'] if r['saved']]:
            case=cases[run['data_seed']];events=[e for b in stream(case,run['scenario']) for e in b['events']]
            # Teaching sequence is harness input; each Learner.answer sees only its next answer.
            teaching=[{'context':e['context'],'label':e['teacher_label']} for e in events]
            desc={'method':run['method'],'dimension':run['dimension'],'seed':run['code_seed'],'teaching':teaching,
                  'checkpoints':{str(v['step']):name for name,v in run['saved'].items()}}
            write(trainer/'input.json',desc)
            code="import json;from ss_online.learning import Learner;d=json.load(open('input.json',encoding='utf-8'));s=Learner.start(d['method'],d['dimension'],d['seed'],'replay-fixed');trace=[]\nfor r in d['teaching']:\n q=s.question(r['context'])['request'];s,a=s.answer(q,{'schema':'plm-ss-online-feedback-01','request_id':q['request_id'],'source':'external_teacher','label':r['label']});trace.append({'before':{k:a['before'][k] for k in ('tentative','accepted')},'after':{k:a['after'][k] for k in ('tentative','accepted')}})\n if str(s.step) in d['checkpoints']:s.save(d['checkpoints'][str(s.step)])\nprint(json.dumps(trace))"
            stdout,_=command(['-c',code],trainer,out/(run['method']+'-SEQUENTIAL.log'))
            replay_trace=json.loads(stdout);assert replay_trace==[{k:r[k] for k in ('before','after')} for r in run['trace']];replayed+=len(replay_trace)
            (trainer/'input.json').unlink()
            context=[r['context'] for g in case['groups'].values() for r in g]+case['unknown']
            for name,meta in run['saved'].items():
                original=Learner.load(ROOT/'results'/name);refit=Learner.load(trainer/name)
                diff=float(np.max(np.abs(original.model.weights-refit.model.weights)))
                assert diff==0 and original.fingerprint==refit.fingerprint==meta['fingerprint']
                assert original.model.predict(context)==refit.model.predict(context)
                comparisons[name]={'contexts':len(context),'coefficient_difference':diff,'strict_fingerprint_equal':True,'replay_buffer_and_history_equal':original.state==refit.state}
                shutil.copytree(ROOT/'results'/name/'model',runtime/name);write(runtime/'query.json',context)
                stdout,_=command(['-m','ss_online','query','--model',name,'--input','query.json'],runtime,out/(name+'-QUERY.log'),(0,2))
                assert json.loads(stdout)==original.model.predict(context);(runtime/'query.json').unlink()
        command(['-c',"from pathlib import Path;import sys;from ss_online.model import Model;assert not Path('ss_online/learning.py').exists();assert not Path('data').exists();assert not Path('evaluation').exists();assert not list(Path('.').rglob('learner.json'));assert not any('learning' in s for s in sys.modules);print('Predictor has no learner, replay buffer, teacher sequence, evaluator or truth')"],runtime,out/'RUNTIME_BOUNDARY.log')
        saved_run=next(r for r in result['runs'] if 'delta-A' in r['saved']);case=cases[saved_run['data_seed']]
        event=[e for b in stream(case,'clean') for e in b['events']][256]
        original=Learner.load(ROOT/'results/delta-A');req=original.question(event['context'])['request'];fb=feedback(req,event['teacher_label']);expected,_=original.answer(req,fb)
        write(trainer/'request.json',req);write(trainer/'feedback.json',fb)
        command(['-m','ss_online','teach','--learner','delta-A','--request','request.json','--feedback','feedback.json','--out','resumed'],trainer,out/'RESUME_ONE.log')
        assert Learner.load(trainer/'resumed').fingerprint==expected.fingerprint
        command(['-m','ss_online','teach','--learner','resumed','--request','request.json','--feedback','feedback.json','--out','stale-output'],trainer,out/'STALE_REQUEST.log',(2,))
        assert not (trainer/'stale-output').exists()
        (trainer/'feedback.json').unlink();write(trainer/'feedback.json',dict(fb,source='model_prediction'))
        command(['-m','ss_online','teach','--learner','delta-A','--request','request.json','--feedback','feedback.json','--out','pseudo-output'],trainer,out/'PSEUDO_FEEDBACK.log',(2,))
        assert not (trainer/'pseudo-output').exists()
    count=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        manifest=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files']
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='RELEASE_MANIFEST.json'}
        assert manifest==actual;count=len(actual)
    report={'status':'passed','unit_tests':tests,'freeze_hash':frozen,'result_digest':claimed,'raw_probe_arrays_rechecked':probes,
            'isolated_sequential_presentations':replayed,'models':comparisons,'prediction_without_teacher_or_replay':True,
            'cli_resume_matches':True,'stale_and_pseudo_feedback_rejected_without_output':True,'manifest_files':count,
            'vendor_manifest_files':len(old),'all_150_trajectories_rerun_here':False,'linux_tested':False,'p1_s1_integrated':False,'eligible_for_inference':False}
    write(out/'VERIFICATION.json',report);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
