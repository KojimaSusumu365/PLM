"""Recompute every outcome, reconstruct SS coefficients, and isolate generation."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from ss_document.runtime import DocumentModel
from ss_document.training import train
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.cases import corpus,INVALID
from evaluation.experiment import trial,adapt_legacy,disturbances,signal_hash


def copy_generator(target):
    specs={'ss_document':['__init__.py','contract.py','codec.py','runtime.py','__main__.py'],
           'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
           'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    for package,files in specs.items():
        p=target/package;p.mkdir(parents=True,exist_ok=True)
        for name in files:shutil.copy2(ROOT/package/name,p/name)


def run(out):
    verify();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    ev=read(ROOT/'results/EVALUATION.json');cases=read(ROOT/'results/CASES.json');assert cases==corpus('evaluation',12)
    case_by={c['id']:c for c in cases};models={};rows=0;signals=0;generated=0
    for spec in ev['models']:
        m=DocumentModel.load(ROOT/'results/models'/spec['id']);assert m.fingerprint==spec['fingerprint'];models[spec['id']]=m
    with np.load(ROOT/'results/SIGNALS.npz',allow_pickle=False) as stored:
        expected_keys=set()
        for r in ev['rows']:
            model=models[r['model_id']];actual,arrays=trial(model,case_by[r['case_id']],r['stage']=='primary')
            wanted={k:v for k,v in r.items() if k not in ('model_id','stage','array_prefix')};assert actual==wanted
            rows+=1;generated+=len(r['outputs'])+1
            for key,v in arrays.items():
                name=r['array_prefix']+'-'+key;expected_keys.add(name);np.testing.assert_array_equal(v,stored[name]);signals+=1
        for p in ev['probes']:
            model=models[p['model_id']];si=int(p['model_id'][1]);meaning=next(c['meaning'] for c in cases if len(c['meaning']['events'])==3)
            rr,arrays=disturbances(model,meaning,900+si);assert rr==p['signals']
            for key,v in arrays.items():
                name=p['model_id']+'-probe-'+key;expected_keys.add(name);np.testing.assert_array_equal(v,stored[name]);signals+=1
            assert p['invalid']==[{'text':t,'result':model.read(t)} for t in INVALID]
        assert set(stored.files)==expected_keys
    old=read(ROOT/'data/evaluation.json');legacy=0
    for expected,case in zip(ev['legacy_regression'],old,strict=True):
        row,_=trial(models['s0-c0'],{'id':case['id'],'text':case['text'],'meaning':adapt_legacy(case['meaning'])},False)
        assert row==expected;legacy+=1
    # Refit on a fresh directory with code and teacher pairs only: no old models, reader or oracle.
    fitroot=out/'refit';fitroot.mkdir()
    for pkg in ('ss_document','plm_l1_v09'):
        shutil.copytree(ROOT/pkg,fitroot/pkg,ignore=shutil.ignore_patterns('reader.py','__pycache__'))
    for name in ('component_train.json','temporal_train.json','lexicon.json'):shutil.copy2(ROOT/'data'/name,fitroot/name)
    fitcmd=[sys.executable,'-B','-m','ss_document','train','--component-pairs','component_train.json','--temporal-pairs','temporal_train.json','--lexicon','lexicon.json','--out','model']
    p=subprocess.run(fitcmd,cwd=fitroot,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
    fitmodel=DocumentModel.load(fitroot/'model');assert fitmodel.fingerprint==models['s0-c0'].fingerprint
    # Reader/trainer/evaluator-free generator. No original text or meaning JSON is transferred.
    groot=out/'generator';groot.mkdir();copy_generator(groot);shutil.copytree(ROOT/'results/models/s0-c0',groot/'model')
    isolated=[]
    for n in (2,3):
        case=next(c for c in cases if len(c['meaning']['events'])==n);pkt=models['s0-c0'].read(case['text'])['packet']
        write(groot/f'packet{n}.json',pkt)
        command=[sys.executable,'-B','-m','ss_document','generate','--model','model','--packet',f'packet{n}.json','--order','reverse']
        proc=subprocess.run(command,cwd=groot,capture_output=True,text=True,encoding='utf-8');assert proc.returncode==0,proc.stderr
        actual=json.loads(proc.stdout);expected=models['s0-c0'].generate(pkt,'reverse')
        assert actual==expected
        isolated.append({'count':n,'command':command,'packet_sha256':signal_hash(pkt),'result':actual,
                         'no_event_count_or_goals_supplied':True})
    write(out/'ISOLATED_GENERATION.json',isolated)
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        expected=read(ROOT/'RELEASE_MANIFEST.json')['files']
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json' and '__pycache__' not in p.parts}
        assert actual==expected;manifest=len(actual)
    summary={'passed':True,'models_loaded':len(models),'input_records_recomputed':rows,'generation_requests_recomputed':generated,
             'signal_arrays_equal':signals,'legacy_regression_records':legacy,'isolated_refit_fingerprint_equal':True,
             'isolated_generation_cases':len(isolated),'manifest_files_checked':manifest,'eligible_for_inference':False}
    write(out/'VERIFY.json',summary);print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
