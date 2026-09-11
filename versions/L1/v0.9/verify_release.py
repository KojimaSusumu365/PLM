"""Exact artifact integrity and separately selected functional reproducibility."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from evaluation.support import ROOT,data,parse
from evaluation.integrity import verify_freeze,manifest_check,sha
from evaluate import judge
from plm_l1_v09.component.algebra import digest
from plm_l1_v09.runtime import TemporalModel,PACKET_FIELDS
from plm_l1_v09.portability import compare

V08_SHA='b672639e0e734230ffe1c4fef781aeafe10e4b68e9ba5ce9fc34b0c5646fd751'

def write(p,value):
    with Path(p).open('x',encoding='utf-8') as f: f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def run(args,cwd,out,label,expected=0,timeout=900):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH',None)
    r=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,text=True,encoding='utf-8',capture_output=True,timeout=timeout)
    with (out/(label+'.log')).open('x',encoding='utf-8') as f: f.write(r.stdout+r.stderr)
    if r.returncode!=expected: raise ValueError(label+': '+(r.stdout+r.stderr)[-5000:])
    return r.stdout,r.stderr

def copy_package(target,excluded):
    for p in (ROOT/'plm_l1_v09').rglob('*.py'):
        if p.name in excluded or '__pycache__' in p.parts: continue
        dest=target/'plm_l1_v09'/p.relative_to(ROOT/'plm_l1_v09'); dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,dest)

def vendor_check(legacy,out):
    path=ROOT/'vendor'/'PLM-L1-v0.8.zip'
    if sha(path)!=V08_SHA: raise ValueError('vendor_archive_hash_mismatch')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None: raise ValueError('vendor_crc_failure')
        prefix='PLM-L1-v0.8/'
        files=json.loads(z.read(prefix+'RELEASE_MANIFEST.json'))['files']
        actual={p.filename[len(prefix):]:hashlib.sha256(z.read(p)).hexdigest() for p in z.infolist()
                if not p.is_dir() and p.filename!=prefix+'RELEASE_MANIFEST.json'}
        if files!=actual: raise ValueError('vendor_manifest_mismatch')
        report={'sha256':V08_SHA,'crc_valid':True,'manifest_files':len(files),'legacy_execution_requested':legacy}
        if legacy:
            with tempfile.TemporaryDirectory(prefix='l09old-') as folder:
                base=Path(folder).resolve(); names=[]
                for item in z.infolist():
                    dest=(base/item.filename).resolve()
                    if not dest.is_relative_to(base) or not item.filename.startswith(prefix) or len(str(dest))>=250:
                        raise ValueError('unsafe_or_overlong_vendor_member')
                    names.append(str(dest).casefold())
                if len(names)!=len(set(names)): raise ValueError('duplicate_vendor_path')
                z.extractall(base)
                run(['verify_release.py','--out',str(base/'verification')],base/'PLM-L1-v0.8',out,'LEGACY_RELEASE',timeout=1200)
                verified=json.loads((base/'verification'/'VERIFICATION.json').read_text(encoding='utf-8'))
                report['test_counts']=verified['test_counts']; report['status']=verified['status']
    return report

def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); p.add_argument('--mode',choices=('strict','functional'),default='strict')
    p.add_argument('--legacy',action='store_true'); a=p.parse_args()
    out=Path(a.out).resolve()
    if out==ROOT or out.is_relative_to(ROOT): raise ValueError('verification_output_must_be_outside_release')
    out.mkdir(parents=True,exist_ok=False)
    freeze=verify_freeze()
    result=json.loads((ROOT/'results'/'EVALUATION.json').read_text(encoding='utf-8')); claimed=result.pop('result_digest')
    if digest(result)!=claimed or result['freeze_hash']!=freeze or judge(result)!=result['checks'] or not all(c['passed'] for c in result['checks']):
        raise ValueError('result_integrity_or_acceptance_failure')
    model=TemporalModel.load(ROOT/'results'/'model')
    if model.fingerprint!=result['model_fingerprint']: raise ValueError('saved_model_mismatch')
    stdout,stderr=run(['-m','unittest','discover','-s','tests','-v'],ROOT,out,'UNIT_TESTS')
    tests=int(re.search(r'Ran (\d+) tests',stdout+stderr).group(1)); print('unit tests',tests,flush=True)
    train=out/'training-only'; copy_package(train,{'reader.py'})
    for name in ('component_train','temporal_train','lexicon'): shutil.copyfile(ROOT/'data'/(name+'.json'),train/(name+'.json'))
    assertion="from pathlib import Path; import importlib.util; assert not Path('data').exists(); assert all(importlib.util.find_spec(n) is None for n in ('evaluation','plm_l1_v09.reader','plm_l1_v09.component.reader')); print('only explicit pairs and lexicon; no reader, evaluator, prior weights or dependency gold')"
    run(['-c',assertion],train,out,'TRAINING_BOUNDARY')
    run(['-m','plm_l1_v09','train','--component-pairs','component_train.json','--temporal-pairs','temporal_train.json','--lexicon','lexicon.json',
         '--seed',model.meta['seed'],'--selection-seed',model.component.meta['selector_seed'],'--selection-dimension',str(model.component.meta['selector_dimension']),
         '--selector','ss','--out','model'],train,out,'PAIR_TRAINING')
    candidate=TemporalModel.load(train/'model')
    # All 816 unique old evaluation surfaces, plus rejection probes. Not a Linux run.
    texts=sorted({r['text'] for r in data('evaluation')})+['','太郎が花子を助けた。','太郎が花子を助けた。その後、彼が花子を助けた。']
    functional=compare(model,candidate,texts)
    if not functional['functional_passed']: raise ValueError('functional_refit_mismatch')
    if a.mode=='strict' and not functional['exact_model_fingerprint_equal']: raise ValueError('strict_refit_fingerprint_mismatch')
    read_dir=out/'reading-only'; copy_package(read_dir,{'training.py','selection.py'}); shutil.copytree(train/'model',read_dir/'model')
    gen_dir=out/'generation-only'; copy_package(gen_dir,{'reader.py','training.py','selection.py'}); shutil.copytree(train/'model',gen_dir/'model')
    assertion="from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('evaluation','plm_l1_v09.reader','plm_l1_v09.training','plm_l1_v09.selection','plm_l1_v09.component.reader','plm_l1_v09.component.training')); assert not Path('component_train.json').exists(); print('no reader, learner, selector, corpus or oracle; structural helpers remain')"
    run(['-c',assertion],gen_dir,out,'GENERATION_BOUNDARY')
    demos=[]
    for i,text in enumerate(('太郎が花子を助けた。その後、花子が健太を褒めた。','太郎が花子を助けた。花子が健太を褒めた。','太郎が太郎を助けた。その前に、花子が健太を褒めた。')):
        name=f'packet-{i}.json'
        run(['-m','plm_l1_v09','read','--model','model','--text',text,'--out',name],read_dir,out,f'READ_{i}')
        packet=json.loads((read_dir/name).read_text(encoding='utf-8'))
        if set(packet)!=PACKET_FIELDS: raise ValueError('non_numeric_transfer')
        shutil.copyfile(read_dir/name,gen_dir/name)
        stdout,_=run(['-m','plm_l1_v09','generate','--model','model','--packet',name,'--order','reverse','--goals','object','subject'],gen_dir,out,f'GENERATE_{i}')
        generated=json.loads(stdout); target=parse(text); target['events'].reverse(); target['goals']=['object','subject']
        if target['relation']!='unknown': target['relation']='after' if target['relation']=='before' else 'before'
        if parse(generated['text'])!=target: raise ValueError('isolated_roundtrip_mismatch')
        demos.append({'input_for_verifier_only':text,'output':generated['text'],'semantic_match':True})
    run(['-m','plm_l1_v09','read','--model','model','--text','太郎が花子を助けた。その後、彼が花子を助けた。','--out','forbidden.json'],read_dir,out,'ATOMIC_ABSTAIN',expected=2)
    if (read_dir/'forbidden.json').exists(): raise ValueError('partial_packet_written')
    vendor=vendor_check(a.legacy,out)
    manifest=manifest_check() if (ROOT/'RELEASE_MANIFEST.json').exists() else 'not_yet_packaged'
    report={'status':'passed','mode':a.mode,'source_freeze':freeze,'result_digest':claimed,'unit_tests':tests,
            'functional_comparison':functional,'exact_artifact_manifest_files':manifest,'vendor':vendor,
            'pair_training_without_reader_or_evaluator':True,'generation_without_reader_trainer_selector':True,
            'numeric_packet_only_transfer':True,'atomic_abstention':True,'demos':demos,'linux_execution_performed':False,
            'old_numeric_evaluation_rerun':False,'new_numeric_evaluation_rerun':False,
            'scope':'Integrity and refit/function/CLI verification. Run evaluate.py separately for complete v0.9 numerical rerun.'}
    write(out/'VERIFICATION.json',report); print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
