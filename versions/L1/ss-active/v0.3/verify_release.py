"""Recompute all saved correlations/metrics; teacher-free export; isolated exact replay."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from ss_multicode.algebra import canonical, digest
from ss_trace.runtime import State, choice
from ss_trace.learning import teach
from evaluation.cases import make_case, teaching, probes
from evaluation.integrity import ROOT, write, sha, verify_freeze
from evaluation.metrics import measure


def verify(results, out):
    verify_freeze();results=Path(results);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    ev=json.loads((results/'EVALUATION.json').read_text(encoding='utf-8'))
    cases=json.loads((results/'CASES.json').read_text(encoding='utf-8'))
    plans=json.loads((results/'PLANS.json').read_text(encoding='utf-8'))
    case_by={(c['seed'],c['size']):c for c in cases};plan_by={p['base_id']:p for p in plans}
    for c in cases:assert c==make_case(c['seed'],c['size'])
    expected_arrays=set();states=0;metric_checks=0;passive_pairs=0;drift_pairs=0;replay_models=0;replay_teachers=0
    snapshots={};metric_rows=[]
    with np.load(results/'SCORES.npz',allow_pickle=False) as arrays:
        for run in ev['runs']:
            case=case_by[run['data_seed'],run['size']];pp=probes(case);pool_ids={r['id'] for r in case['pool']}
            plan=plan_by[run['base_id']]
            assert run['plan_digest']==digest(plan['requests'])
            assert [r['id'] for r in run['trace']]==[r['id'] for r in plan['requests']]
            for cp in run['checkpoints']:
                expected_truth={r['id']:r['label'] for g in 'ABCDE' for r in case['groups'][g]}
                if run['world']=='drift_after_q16' and cp['name'] not in ('base','q16'):
                    for k in plan['changed_ids']:expected_truth[k]=str((int(expected_truth[k])+1)%4)
                assert cp['world_truth']==expected_truth
                state=State.load(results/cp['state']);assert state.fingerprint==cp['fingerprint'];states+=1
                main,aux=state.raw([r['context'] for r in pp])
                for suffix,v in (('_main',main),('_aux',aux)):
                    key=cp['array']+suffix;expected_arrays.add(key);np.testing.assert_array_equal(arrays[key],v)
                actual=measure(main,aux,pp,state.ledger,state.step,cp['last_teacher'],cp['world_truth'],
                               cp['first_corrected'],cp['taught_correct'],case['size'],pool_ids)
                assert actual==cp['metrics'];metric_checks+=1
                snapshots[run['base_id'],run['arm'],run['world'],cp['name']]=state
                metric_rows.append({'run_id':run['run_id'],'size':run['size'],'arm':run['arm'],'world':run['world'],
                                    'checkpoint':cp['name'],'metrics':actual})
            # Replay every acquisition/background from each saved base. Teacher labels below are evaluator-only.
            s=State.load(results/run['checkpoints'][0]['state']);last={};correct=set();fixed=set()
            original={r['id']:r['label'] for g in 'ABCDE' for r in case['groups'][g]};truth=dict(original)
            for i,e in enumerate(run['trace']):
                if i==16:
                    if run['world']=='drift_after_q16':
                        for k in plan['changed_ids']:truth[k]=str((int(truth[k])+1)%4)
                    for item in teaching(case,'D',2):teach(s,**item,kind='background');replay_teachers+=1
                    assert s.fingerprint==next(c for c in run['checkpoints'] if c['name']=='post_D')['fingerprint']
                before=s.raw([e['context']])[0];np.testing.assert_array_equal(before,np.asarray(e['before']))
                assert e['teacher_label']==truth[e['id']]
                teach(s,e['context'],e['teacher_label']);replay_teachers+=1
                after=s.raw([e['context']])[0];np.testing.assert_array_equal(after,np.asarray(e['after']))
                pre=int(choice(before)['tentative'][0]);post=int(choice(after)['tentative'][0]);y=int(e['teacher_label'])
                last[e['id']]=e['teacher_label']
                if post==y:correct.add(e['id'])
                if i<16 and pre>=0 and pre!=y and post==y:fixed.add(e['id'])
                if i in (15,31):
                    cp=next(c for c in run['checkpoints'] if c['name']==('q16' if i==15 else 'q32'))
                    assert s.fingerprint==cp['fingerprint'];assert cp['last_teacher']==last
                    assert cp['taught_correct']==sorted(correct);assert cp['first_corrected']==sorted(fixed)
            for item in teaching(case,'E',2):teach(s,**item,kind='background');replay_teachers+=1
            assert s.fingerprint==run['checkpoints'][-1]['fingerprint'];replay_models+=1
        assert set(arrays.files)==expected_arrays
    for p in plans:
        bid=p['base_id']
        assert len(set(p['changed_ids']))==16
        assert p['changed_ids'][:8]==[r['id'] for r in p['requests'][:8]]
        assert not set(p['changed_ids'][8:]) & {r['id'] for r in p['requests'][:16]}
        for arm in ('main512','main640','main384','main512_pair','main384_pair','main512_bank'):
            for stage in ('base','q16','drift_only'):
                assert snapshots[bid,arm,'stationary',stage].fingerprint==snapshots[bid,arm,'drift_after_q16',stage].fingerprint
                drift_pairs+=1
            for world in ('stationary','drift_after_q16'):
                a=snapshots[bid,arm,world,'q16'];b=snapshots[bid,arm,world,'drift_only']
                assert a.fingerprint==b.fingerprint
        for world in ('stationary','drift_after_q16'):
            for stage in ('base','q16','drift_only','post_D','q32','post_E'):
                for auxarm in ('main512_pair','main512_bank'):
                    np.testing.assert_array_equal(snapshots[bid,'main512',world,stage].main,snapshots[bid,auxarm,world,stage].main);passive_pairs+=1
                np.testing.assert_array_equal(snapshots[bid,'main384',world,stage].main,snapshots[bid,'main384_pair',world,stage].main);passive_pairs+=1
    # Teacher-free subprocess: only algebra/model support and prediction runtime; no learning/evaluation/data.
    isolated=out/'teacher-free';(isolated/'ss_trace').mkdir(parents=True);(isolated/'ss_multicode').mkdir()
    for package,names in [('ss_trace',['__init__.py','runtime.py','__main__.py']),('ss_multicode',['__init__.py','algebra.py','model.py'])]:
        for name in names:shutil.copy2(ROOT/package/name,isolated/package/name)
    selected=next(r for r in ev['runs'] if r['arm']=='main512_pair' and r['size']==128 and r['world']=='stationary')
    path=results/selected['checkpoints'][-1]['state'];shutil.copytree(path,isolated/'state')
    inputs=[r['context'] for r in probes(case_by[selected['data_seed'],selected['size']])]
    write(isolated/'input.json',inputs)
    proc=subprocess.run([sys.executable,'-B','-m','ss_trace','observe','--state','state','--input','input.json'],cwd=isolated,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)==State.load(path).observe(inputs)
    # Refit all unique base states from external teachers, not from saved coefficients.
    base_fits=0;base_teachers=0
    for p in plans:
        case=case_by[p['data_seed'],p['size']]
        for arm in ('main512','main640','main384','main512_pair','main384_pair','main512_bank'):
            s=State(arm,p['code_seed'])
            for e in teaching(case,'ABC',4):teach(s,**e,kind='background');base_teachers+=1
            assert s.fingerprint==snapshots[p['base_id'],arm,'stationary','base'].fingerprint;base_fits+=1
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        files=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files']
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json' and '__pycache__' not in p.parts}
        assert actual==files;manifest=len(files)
    summary={'passed':True,'saved_states':states,'raw_arrays':len(expected_arrays),'metrics_recomputed':metric_checks,
             'passive_main_equal_checks':passive_pairs,'blind_world_equal_checks':drift_pairs,
             'trajectory_replays':replay_models,'replay_teachers':replay_teachers,'base_refits':base_fits,'base_refit_teachers':base_teachers,
             'teacher_free_predictions':len(inputs),'manifest_files_checked':manifest,
             'eligible_for_inference':False}
    write(out/'VERIFY.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',default=str(ROOT/'results'));p.add_argument('--out',required=True)
    a=p.parse_args();verify(a.results,a.out)
