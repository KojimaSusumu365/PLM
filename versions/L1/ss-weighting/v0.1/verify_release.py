"""Verify frozen code, raw scores, isolated refits and predictor-only execution."""
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
from plm_l1_v013.algebra import digest
from plm_l1_v013.core import Model
from plm_l1_v013.training import fit as original_fit
from ss_weighting.memory import Memory
from evaluation.weight_cases import memory_case
from evaluation.legacy_cases import queries
from evaluation.weight_integrity import ROOT, sha, verify, write
from evaluate_weights import metrics


def command(args, cwd, log, accepted=(0,)):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH',None)
    p=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,text=True,encoding='utf-8',capture_output=True,timeout=180)
    log.write_text(p.stdout+p.stderr,encoding='utf-8')
    if p.returncode not in accepted: raise ValueError(f'failed {log.name}: {p.stderr[-2000:]}')
    return p.stdout,p.stderr


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=verify()
    baseline=json.loads((ROOT/'verification/BASELINE.json').read_text(encoding='utf-8'))
    assert all(sha(ROOT/n)==h for n,h in baseline['copied_files'].items())
    vendor=ROOT/'vendor/PLM-L1-v0.13.zip'
    assert sha(vendor)=='e4251ee2c510c028f316e1428cb722d5e2eac40d26dfe307b50fd75a647606c6'
    with zipfile.ZipFile(vendor) as z:
        assert z.testzip() is None
        old=json.loads(z.read('PLM-L1-v0.13/RELEASE_MANIFEST.json'))['files']
        assert all(hashlib.sha256(z.read('PLM-L1-v0.13/'+n)).hexdigest()==h for n,h in old.items())
    stdout,stderr=command(['-m','unittest','discover','-s','tests','-v'],ROOT,out/'UNIT_TESTS.log')
    tests=int(re.search(r'Ran (\d+) tests',stdout+stderr).group(1))
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    claimed=result.pop('result_digest')
    assert digest(result)==claimed and result['freeze_hash']==frozen and result['all_contract_checks_passed']
    with np.load(ROOT/'results/SCORES.npz',allow_pickle=False) as z:
        assert set(z.files)==set(result['score_arrays'])
        for key,entry in result['score_arrays'].items():
            arr=z[key]
            assert list(arr.shape)==entry['shape'] and hashlib.sha256(arr.astype('<f8').tobytes()).hexdigest()==entry['sha256']
        for r in result['memory']:
            case=memory_case(r['data_seed'],r['known_count'])
            truth=[x['label'] for x in case['teachers']]
            for c in r['conditions']:
                assert metrics(z[c['scores_array']],list('0123'),truth,r['known_count'])==c['metrics']
    comparisons={}; isolated=[]
    with tempfile.TemporaryDirectory(prefix='swverify-') as temp:
        base=Path(temp).resolve();trainer=base/'training';trainer.mkdir();runtime=base/'runtime';runtime.mkdir()
        for package in ('ss_weighting','plm_l1_v013'):
            shutil.copytree(ROOT/package,trainer/package,ignore=shutil.ignore_patterns('__pycache__'))
        for package,names in {'ss_weighting':('__init__.py','memory.py','__main__.py'),
                              'plm_l1_v013':('__init__.py','algebra.py','core.py')}.items():
            (runtime/package).mkdir()
            for n in names:shutil.copyfile(ROOT/package/n,runtime/package/n)
        for name,desc in result['saved_models'].items():
            teachers=json.loads((ROOT/'results'/(name+'-teachers.json')).read_text(encoding='utf-8'))
            write(trainer/'teachers.json',teachers)
            code="import json;from ss_weighting.training import fit;r=json.load(open('teachers.json',encoding='utf-8'));m,_=fit(r,dimension="+str(desc['dimension'])+",seed="+repr(desc['code_seed'])+",method="+repr(desc['method'])+");m.save("+repr(name)+")"
            command(['-c',code],trainer,out/(name+'-TRAIN.log'))
            (trainer/'teachers.json').unlink()
            original=Memory.load(ROOT/'results'/name);refit=Memory.load(trainer/name)
            delta=float(np.max(np.abs(original.weights-refit.weights)))
            assert original.fingerprint==refit.fingerprint and delta==0
            case=memory_case(desc['data_seed'],desc['known_count'])
            context=[r['context'] for r in case['teachers']]+case['unknown']
            assert original.predict(context)==refit.predict(context)
            comparisons[name]={'contexts':len(context),'coefficient_difference':delta,'strict_fingerprint_equal':True,'functional_predictions_equal':True}
            shutil.copytree(ROOT/'results'/name,runtime/name)
            write(runtime/'queries.json',context)
            stdout,_=command(['-m','ss_weighting','query','--model',name,'--input','queries.json'],runtime,out/(name+'-QUERY.log'),(0,2))
            assert json.loads(stdout)==original.predict(context)
            (runtime/'queries.json').unlink()
            isolated.append(name)
        taskmap={t['id']:t for t in json.loads((ROOT/'data/v013-evaluation.json').read_text(encoding='utf-8'))}
        for name,desc in result['saved_structured'].items():
            task=taskmap[desc['task_id']];rows=task['initial']
            if desc['budget']:
                oldmodel=original_fit(rows,dimension=2048,seed='evaluation-0',retention='all')[0]
                req=oldmodel.select(task['pool']);rows=rows+[{'context':req['context'],'label':task['teacher_answers'][req['id']]}]
            write(trainer/'teachers.json',rows)
            code="import json;from ss_weighting.training import fit_structured;r=json.load(open('teachers.json',encoding='utf-8'));m,_=fit_structured(r,dimension="+str(desc['dimension'])+",seed="+repr(desc['seed'])+",method="+repr(desc['method'])+");m.save("+repr(name)+")"
            command(['-c',code],trainer,out/(name+'-TRAIN.log'))
            (trainer/'teachers.json').unlink()
            original=Model.load(ROOT/'results'/name);refit=Model.load(trainer/name)
            delta=max([float(np.max(np.abs(u['weights']-v['weights']))) for u,v in zip(original.members,refit.members)]+[0.])
            context=[q['context'] for _,group in queries(task) for q in group]
            assert original.fingerprint==refit.fingerprint and delta==0 and original.predict_many(context)==refit.predict_many(context)
            comparisons[name]={'contexts':len(context),'coefficient_difference':delta,'strict_fingerprint_equal':True,'functional_predictions_equal':True}
            shutil.copytree(ROOT/'results'/name,runtime/name)
            write(runtime/'queries.json',context)
            code="import json;from plm_l1_v013.core import Model;m=Model.load("+repr(name)+");print(json.dumps(m.predict_many(json.load(open('queries.json',encoding='utf-8')))))"
            stdout,_=command(['-c',code],runtime,out/(name+'-QUERY.log'))
            assert json.loads(stdout)==original.predict_many(context)
            (runtime/'queries.json').unlink()
            isolated.append(name)
        command(['-c',"from pathlib import Path;import sys;from ss_weighting.memory import Memory;assert not Path('evaluation').exists();assert not Path('data').exists();assert not Path('ss_weighting/training.py').exists();assert not Path('ss_weighting/learning.py').exists();assert not Path('plm_l1_v013/training.py').exists();assert not any('training' in x or 'learning' in x for x in sys.modules);print('No trainers, solver, teachers, evaluator or truth in runtime')"],runtime,out/'RUNTIME_BOUNDARY.log')
    manifest_count=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        manifest=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text(encoding='utf-8'))['files']
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='RELEASE_MANIFEST.json'}
        assert actual==manifest
        manifest_count=len(actual)
    report={'status':'passed','unit_tests':tests,'new_tests':tests-54,'inherited_v013_tests':54,
            'freeze_hash':frozen,'result_digest':claimed,'score_arrays_rechecked':len(result['score_arrays']),
            'isolated_refits':comparisons,'prediction_only_models':isolated,'runtime_has_no_training_or_teacher_data':True,
            'manifest_files':manifest_count,'old_v013_vendor_manifest_files':len(old),
            'full_evaluation_rerun_by_this_command':False,'linux_tested':False,'p1_s1_integrated':False,'eligible_for_inference':False}
    write(out/'VERIFICATION.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
