"""Check reported tables against results and execute the shipped one-teacher example."""
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,verify,sha
from ss_active.session import Session

verify()
report=(ROOT/'REPORT.md').read_text(encoding='utf-8')
assert all(s not in report for s in ('ここに記載','TODO','FIXME'))
rows=json.loads((ROOT/'verification/SUMMARY.json').read_text(encoding='utf-8'))['rows']
def row(size,world,strategy,budget,stage):
    return next(r for r in rows if (r['size'],r['scenario'],r['strategy'],r['budget'],r['stage'])==(size,world,strategy,budget,stage))
labels={'random':'無作為','ambiguity':'平均曖昧さ','disagreement':'符号不一致'}
checked=0
def table(values):
    global checked
    line='|'+'|'.join(map(str,values))+'|'
    assert line in report,line
    checked+=1
for stage,jstage in (('after_acquisition','D学習前'),('after_challenge','D学習後')):
    for strategy,budget in [('random',0),('random',32),('ambiguity',32),('disagreement',32)]:
        r=row(128,'stationary',strategy,budget,stage); g=r['metrics']['groups']['old_all']
        table(['追加教師なし' if budget==0 else labels[strategy]+'32件',jstage,*[g[k] for k in ('tentative_correct','accepted_correct','accepted_wrong','accepted_abstained')],r['metrics']['groups']['never_taught']['unseen_false_accept']])
for budget in (0,4,16,32):
    table([budget,*[str(row(128,'stationary',s,budget,'after_acquisition')['metrics']['groups']['old_all']['accepted_correct'])+' → '+str(row(128,'stationary',s,budget,'after_challenge')['metrics']['groups']['old_all']['accepted_correct']) for s in labels]])
for size in (64,128):
    for strategy in labels:
        r=row(size,'changed_pool16',strategy,32,'after_challenge'); g=r['metrics']['groups']['old_all']
        table([size,labels[strategy],*[g[k] for k in ('accepted_correct','accepted_wrong','accepted_abstained')],r['teacher_selection']['changed_items_selected'],r['metrics']['groups']['changed_pool']['tentative_correct']])
for world,jworld in (('stationary','固定'),('changed_pool16','変更')):
    for strategy in labels:
        r=row(128,world,strategy,32,'after_challenge'); t=r['teacher_selection']; c=r['metrics']['correction_recurrence']
        table([jworld,labels[strategy],t['pre_tentative_wrong'],t['direct_wrong_to_correct'],str(c['again_wrong'])+'/'+str(t['direct_wrong_to_correct'])])
for strategy in labels:
    table([labels[strategy],*[row(128,'stationary',strategy,32,stage)['metrics']['groups']['protected_old']['accepted_correct'] for stage in ('after_acquisition','after_challenge')]])
bench=json.loads((ROOT/'verification/BENCHMARK.json').read_text(encoding='utf-8'))['rows']
for strategy in labels:
    b=[r for r in bench if r['strategy']==strategy]
    table([labels[strategy],f"{statistics.median(r['selection_seconds_32_requests'] for r in b):.3f}秒",f"{statistics.median(r['response_seconds_32_teachers_including_selection_revalidation'] for r in b):.3f}秒",f"{statistics.median(r['query_ms_per_context_batched128'] for r in b):.3f}ms"])
env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');env.pop('PYTHONPATH',None)
with tempfile.TemporaryDirectory(prefix='asdoc-') as td:
    temp=Path(td).resolve(); commands=[]
    def run(args):
        p=subprocess.run([sys.executable,'-B','-m','ss_active',*map(str,args)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
        assert p.returncode==0,p.stderr+p.stdout
        commands.append({'command':args[0],'exit_code':p.returncode})
        return json.loads(p.stdout)
    request=run(['ask','--session','results/s128-disagreement-b0','--out',temp/'request.json'])
    assert request==json.loads((ROOT/'examples/request.json').read_text(encoding='utf-8'))
    updated=run(['teach','--session','results/s128-disagreement-b0','--request',temp/'request.json','--feedback','examples/feedback.json','--out',temp/'updated'])
    expected=json.loads((ROOT/'examples/EXPECTED.json').read_text(encoding='utf-8'))
    assert updated['fingerprint']==expected['session_after']==Session.load(temp/'updated').fingerprint
    prediction=run(['query','--model',temp/'updated/learner/model','--input','examples/queries.json'])
    assert prediction==expected['prediction_after']
    selection=run(['select','--model','results/s128-disagreement-b0/learner/model','--pool','examples/pool.json','--strategy','disagreement','--seed','active-acq-0','--index','0'])
    assert selection==request['selection']
write(ROOT/'verification/DOCUMENT_QA.json',{'status':'passed','table_rows_verified_against_json':checked,'cli_examples':commands,
    'report_sha256':sha(ROOT/'REPORT.md'),'readme_sha256':sha(ROOT/'README.md'),'prediction_after_teacher_matches':True})
print(json.dumps({'table_rows_checked':checked,'cli_examples_checked':len(commands),'status':'passed'}))
