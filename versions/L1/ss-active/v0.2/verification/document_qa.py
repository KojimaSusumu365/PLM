import json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,sha,verify
from ss_active.session import Session,feedback
verify();report=(ROOT/'REPORT.md').read_text(encoding='utf-8')
assert all(x not in report for x in ('本評価完了後に記載','検証完了後に記載','本評価に基づく結論を記載','TODO','FIXME'))
expected_rows=json.loads((ROOT/'verification/TABLE_ROWS.json').read_text(encoding='utf-8'))
for line in expected_rows:assert line in report,line
selected=json.loads((ROOT/'evaluation/SELECTED.json').read_text(encoding='utf-8'))
for r in selected['development_rows']:
    cfg=r['config'];assert f"|1/{cfg['explore_every']}|{cfg['drop_margin']}|{r['utility']}|" in report
env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');env.pop('PYTHONPATH',None)
commands=[]
with tempfile.TemporaryDirectory(prefix='a2doc-') as td:
    temp=Path(td).resolve()
    def run(args,accepted=(0,)):
        p=subprocess.run([sys.executable,'-B','-m','ss_active',*map(str,args)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=40)
        assert p.returncode in accepted,p.stdout+p.stderr;commands.append({'command':args[0],'exit_code':p.returncode});return json.loads(p.stdout)
    q=run(['ask','--session','examples/before-revisit','--out',temp/'request.json']);assert q==json.loads((ROOT/'examples/request.json').read_text(encoding='utf-8')) and q['selection']['route']=='revisit'
    new=run(['teach','--session','examples/before-revisit','--request',temp/'request.json','--feedback','examples/feedback.json','--out',temp/'updated'])
    expected=json.loads((ROOT/'examples/EXPECTED.json').read_text(encoding='utf-8'));assert new['fingerprint']==expected['session_after']
    prediction=run(['query','--model',temp/'updated/learner/model','--input','examples/queries.json'],(0,2));assert prediction==expected['after']
    state=run(['export','--session','examples/before-revisit','--out',temp/'state.json']);assert state==json.loads((ROOT/'examples/selection-state.json').read_text(encoding='utf-8'))
    selection=run(['select','--model','examples/before-revisit/learner/model','--state',temp/'state.json']);assert selection==q['selection']
    started=run(['start','--learner','results/base-s128','--pool','examples/pool.json','--config','examples/config.json','--strategy','mixed_revisit','--seed','active2-acq-0','--out',temp/'start']);assert Session.load(temp/'start').fingerprint==started['fingerprint']
    case=next(c for c in json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation'] if c['seed']=='active2-final-0' and c['size']==128)
    s=Session.load(ROOT/'examples/before-revisit');e=case['groups']['E'][0];write(temp/'context.json',e['context'])
    bq=run(['background-ask','--session','examples/before-revisit','--input',temp/'context.json','--out',temp/'bq.json']);fb=feedback(bq,e['label']);write(temp/'fb.json',fb)
    bg=run(['background-teach','--session','examples/before-revisit','--request',temp/'bq.json','--feedback',temp/'fb.json','--out',temp/'background']);assert bg['fingerprint']==s.background_answer(bq,fb).fingerprint
write(ROOT/'verification/DOCUMENT_QA.json',{'status':'passed','table_rows_verified_against_json':len(expected_rows)+4,'cli_examples':commands,'report_sha256':sha(ROOT/'REPORT.md'),'readme_sha256':sha(ROOT/'README.md'),'actual_revisit_example_verified':True})
print(json.dumps({'status':'passed','table_rows_checked':len(expected_rows)+4,'cli_commands':len(commands)}))
