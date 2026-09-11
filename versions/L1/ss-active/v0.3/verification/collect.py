"""Release evidence collection, never a training/selection input."""
import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,sha,verify_freeze
from evaluation.cases import probes,teaching
from ss_trace.runtime import State,choice
from ss_trace.learning import question,teacher,answer,teach
from ss_multicode.algebra import digest


def collect(repeat, previous, previous_zip):
    verify_freeze();repeat=Path(repeat);previous=Path(previous)
    one=ROOT/'results'
    files={p.relative_to(one).as_posix():sha(p) for p in one.rglob('*') if p.is_file() and p.name!='PERFORMANCE.json'}
    two={p.relative_to(repeat).as_posix():sha(p) for p in repeat.rglob('*') if p.is_file() and p.name!='PERFORMANCE.json'}
    assert files==two
    write(ROOT/'verification/REPEATABILITY.json',{'passed':True,'byte_identical_files':len(files),
          'files':files,'exclusion':['PERFORMANCE.json'],'result_digest':digest(files)})
    old=json.loads((ROOT/'verification/PREVIOUS_BASELINE.json').read_text(encoding='utf-8'))
    actual={p.relative_to(previous).as_posix():sha(p) for p in previous.rglob('*') if p.is_file()}
    assert old['files']==actual;assert sha(previous_zip)==old['zip_sha256']
    write(ROOT/'verification/PRESERVATION.json',{'passed':True,'previous_files_unchanged':len(actual),'previous_zip_unchanged':True,
          'previous_zip_sha256':old['zip_sha256'],'copied_core_byte_identical':True})
    proc=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0
    write(ROOT/'verification/TESTS.json',{'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),
          'processor':platform.processor(),'other_os_tested':False})
    ev=json.loads((one/'EVALUATION.json').read_text(encoding='utf-8'))
    cases={(c['seed'],c['size']):c for c in json.loads((one/'CASES.json').read_text(encoding='utf-8'))}
    plans={p['base_id']:p for p in json.loads((one/'PLANS.json').read_text(encoding='utf-8'))}
    # Independently regenerate every reference selection plan (no auxiliary or future truth).
    plan_checks=0;reference_teachers=0
    for p in plans.values():
        c=cases[p['data_seed'],p['size']];s=State('main512',p['code_seed']);todo=list(c['pool'])
        truth={r['id']:r['label'] for g in 'ABCDE' for r in c['groups'][g]}
        for e in teaching(c,'ABC',4):teach(s,**e,kind='background')
        for qi,expected in enumerate(p['requests']):
            if qi==16:
                for e in teaching(c,'D',2):teach(s,**e,kind='background')
            margins=choice(s.raw([r['context'] for r in todo])[0])['margin']
            j=min(range(len(todo)),key=lambda j:(float(margins[j]),digest(['active3-plan',c['seed'],p['code_seed'],todo[j]['id']])))
            r=todo.pop(j);assert r==expected;teach(s,r['context'],truth[r['id']]);plan_checks+=1
        reference_teachers+=s.step
    write(ROOT/'verification/REFERENCE_REPLAY.json',{'passed':True,'selections':plan_checks,'teacher_presentations':reference_teachers})
    # A documented, evaluator-selected true relapse example; not an independent success test.
    selected=None
    for run in ev['runs']:
        if run['arm']!='main512_pair' or run['world']!='stationary':continue
        cp=run['checkpoints'][-1];s=State.load(one/cp['state']);keys=cp['taught_correct']
        for key in keys:
            obs=s.observe([s.ledger[key]['context']])[0]
            if obs['ss_disagreement'] and obs['main_tentative']!=int(cp['last_teacher'][key]):
                selected=(run,cp,s,key,obs);break
        if selected:break
    if selected is None:
        run=next(r for r in ev['runs'] if r['arm']=='main512_pair' and r['world']=='stationary')
        cp=run['checkpoints'][-1];s=State.load(one/cp['state']);key=sorted(s.ledger)[0]
        selected=(run,cp,s,key,s.observe([s.ledger[key]['context']])[0])
    run,cp,s,key,obs=selected;context=s.ledger[key]['context'];s.save(ROOT/'examples/state')
    write(ROOT/'examples/queries.json',[context]);write(ROOT/'examples/context.json',context)
    req=question(s,context);feedback=teacher(req,cp['world_truth'][key])
    write(ROOT/'examples/request.json',req);write(ROOT/'examples/feedback.json',feedback)
    before=s.fingerprint;answer(s,req,feedback)
    write(ROOT/'examples/EXPECTED.json',{'chosen_post_hoc_for_demonstration':True,'source_run':run['run_id'],
          'before_fingerprint':before,'before_observation':obs,'after_fingerprint':s.fingerprint,
          'after_observation':s.observe([context])[0], 'note':'One manually requested teacher, not an autonomous detector-driven experiment.'})
    # CLI ask/teach/observe are exercised through separate processes and saved-state resume.
    cli=repeat.parent/'ss-active3-cli-check';cli.mkdir(exist_ok=False)
    commands=[['observe','--state',str(ROOT/'examples/state'),'--input',str(ROOT/'examples/queries.json')],
              ['ask','--state',str(ROOT/'examples/state'),'--input',str(ROOT/'examples/context.json'),'--out',str(cli/'request.json')],
              ['teach','--state',str(ROOT/'examples/state'),'--request',str(cli/'request.json'),'--feedback',str(ROOT/'examples/feedback.json'),'--out',str(cli/'updated')]]
    outputs=[]
    for args in commands:
        p=subprocess.run([sys.executable,'-B','-m','ss_trace',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
        outputs.append({'command':args,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    assert State.load(cli/'updated').fingerprint==s.fingerprint
    write(ROOT/'verification/CLI.json',{'passed':True,'commands':outputs,'updated_fingerprint':s.fingerprint})
    # Serial warm diagnostics benchmark after both full runs; 7 repetitions per arm.
    benchmark=[]
    for arm in ('main512','main640','main384','main512_pair','main384_pair','main512_bank'):
        run=next(r for r in ev['runs'] if r['arm']==arm and r['size']==128 and r['world']=='stationary')
        s=State.load(one/run['checkpoints'][-1]['state']);ctx=[r['context'] for r in probes(cases[run['data_seed'],128])]
        s.observe(ctx);samples=[]
        for _ in range(7):
            t=time.perf_counter();s.observe(ctx);samples.append(time.perf_counter()-t)
        benchmark.append({'arm':arm,'queries_per_call':len(ctx),'samples_seconds':samples,'median_seconds':float(np.median(samples)),
                          'storage':s.storage()})
    write(ROOT/'verification/BENCHMARK.json',{'rows':benchmark,'scope':'Serial7 repeats, one representative high-load saved state, warm atom cache. Includes feature assembly, correlations, decisions and Python result objects. Not total training time/RSS/FLOPs.'})
    print(json.dumps({'repeat_files':len(files),'old_files':len(actual),'reference_selections':plan_checks,'example_run':selected[0]['run_id']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repeat',required=True);p.add_argument('--previous',required=True);p.add_argument('--previous-zip',required=True)
    a=p.parse_args();collect(a.repeat,a.previous,a.previous_zip)
