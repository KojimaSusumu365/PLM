"""v0.10 integrity, independent refit, functional comparison and isolated CLI."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
from evaluation.support import ROOT,data,parse
from evaluation.integrity import verify_freeze,check_manifest,sha
from evaluation.language import training_case
from evaluate import judge
from plm_l1_v010.runtime import CommitteeModel,PACKET_FIELDS
from plm_l1_v010.portability import compare
from plm_l1_v010.base.component.algebra import digest

V09_SHA='08e62cb7251f9cc125cb60691bccb997a4e9ad55c6a4ff27c921e687f3df5bdb'

def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def run(args,cwd,out,label,expected=0,timeout=900):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');env.pop('PYTHONPATH',None)
    r=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,text=True,encoding='utf-8',capture_output=True,timeout=timeout)
    with (out/(label+'.log')).open('x',encoding='utf-8') as f:f.write(r.stdout+r.stderr)
    if r.returncode!=expected:raise ValueError(label+': '+(r.stdout+r.stderr)[-5000:])
    return r.stdout+r.stderr

def copy_package(target,excluded):
    for p in (ROOT/'plm_l1_v010').rglob('*.py'):
        if p.name in excluded or '__pycache__' in p.parts:continue
        dest=target/'plm_l1_v010'/p.relative_to(ROOT/'plm_l1_v010');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)

def vendor(out,execute):
    archive=ROOT/'vendor/PLM-L1-v0.9.zip'
    if sha(archive)!=V09_SHA:raise ValueError('vendor_hash_mismatch')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('vendor_crc_mismatch')
        prefix='PLM-L1-v0.9/';manifest=json.loads(z.read(prefix+'RELEASE_MANIFEST.json'))['files']
        actual={p.filename[len(prefix):]:hashlib.sha256(z.read(p)).hexdigest() for p in z.infolist() if not p.is_dir() and p.filename!=prefix+'RELEASE_MANIFEST.json'}
        if manifest!=actual:raise ValueError('vendor_manifest_mismatch')
        report={'sha256':V09_SHA,'crc_valid':True,'manifest_files':len(manifest),'legacy_execution_requested':execute}
        if execute:
            with tempfile.TemporaryDirectory(prefix='l10old-') as d:
                base=Path(d).resolve();seen=set()
                for item in z.infolist():
                    dest=(base/item.filename).resolve()
                    if not dest.is_relative_to(base) or not item.filename.startswith(prefix) or len(str(dest))>=250 or str(dest).casefold() in seen:raise ValueError('unsafe_vendor_path')
                    seen.add(str(dest).casefold())
                z.extractall(base)
                run(['verify_release.py','--mode','functional','--legacy','--out',str(base/'verified')],base/'PLM-L1-v0.9',out,'LEGACY',timeout=1500)
                old=json.loads((base/'verified/VERIFICATION.json').read_text(encoding='utf-8'))
                report['unit_tests']=old['unit_tests'];report['nested_test_counts']=old['vendor']['test_counts'];report['status']=old['status']
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--mode',choices=('strict','functional'),default='strict');p.add_argument('--legacy',action='store_true');a=p.parse_args()
    out=Path(a.out).resolve()
    if out.is_relative_to(ROOT):raise ValueError('verification_output_must_be_outside_release')
    out.mkdir(parents=True,exist_ok=False);freeze=verify_freeze()
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'));claimed=result.pop('result_digest')
    if digest(result)!=claimed or result['freeze_hash']!=freeze or judge(result)!=result['checks'] or not all(c['passed'] for c in result['checks']):raise ValueError('result_integrity_failure')
    model=CommitteeModel.load(ROOT/'results/model')
    if model.fingerprint!=result['model_fingerprint']:raise ValueError('model_result_mismatch')
    log=run(['-m','unittest','discover','-s','tests','-v'],ROOT,out,'UNIT_TESTS');tests=int(re.search(r'Ran (\d+) tests',log).group(1));print('unit tests',tests,flush=True)
    train=out/'training-only';copy_package(train,{'reader.py'})
    for source,target in (('component_train','component'),('single_development','selection'),('temporal_train','temporal'),('lexicon','lexicon')):shutil.copyfile(ROOT/'data'/(source+'.json'),train/(target+'.json'))
    guard="from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('evaluation','plm_l1_v010.reader','plm_l1_v010.base.reader','plm_l1_v010.base.component.reader')); assert not Path('vendor').exists(); print('explicit train and selection-validation pairs only; no reader, evaluator or saved weights')"
    run(['-c',guard],train,out,'TRAIN_BOUNDARY')
    run(['-m','plm_l1_v010','train','--component-pairs','component.json','--selection-pairs','selection.json','--temporal-pairs','temporal.json','--lexicon','lexicon.json','--selection-seed',model.meta['training']['selection_seed'],'--out','model'],train,out,'ISOLATED_TRAIN')
    candidate=CommitteeModel.load(train/'model')
    # Full 816 distinct standard surfaces plus three rejection probes.
    texts=sorted({r['text'] for r in data('evaluation')})+['','太郎が花子を助けた。','太郎が花子を助けた。その後、彼が花子を助けた。']
    comparison=compare(model,candidate,texts)
    if not comparison['functional_passed'] or (a.mode=='strict' and not comparison['exact_fingerprint_equal']):raise ValueError('refit_mismatch')
    read_dir=out/'reading-only';copy_package(read_dir,{'training.py','selection.py','memory.py'});shutil.copytree(train/'model',read_dir/'model')
    gen_dir=out/'generation-only';copy_package(gen_dir,{'reader.py','training.py','selection.py','memory.py'});shutil.copytree(train/'model',gen_dir/'model')
    guard="from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('evaluation','plm_l1_v010.reader','plm_l1_v010.training','plm_l1_v010.selection','plm_l1_v010.base.reader','plm_l1_v010.base.component.reader')); assert not Path('component.json').exists(); print('no reader, learner, selector, corpus or evaluator; whole-output consensus remains')"
    run(['-c',guard],gen_dir,out,'GENERATION_BOUNDARY')
    demos=[]
    for i,text in enumerate(('太郎が花子を助けた。その後、花子が健太を褒めた。','太郎が太郎を助けた。その前に、花子が健太を褒めた。')):
        name=f'packet-{i}.json';run(['-m','plm_l1_v010','read','--model','model','--text',text,'--out',name],read_dir,out,f'READ_{i}')
        packet=json.loads((read_dir/name).read_text(encoding='utf-8'))
        if set(packet)!=PACKET_FIELDS:raise ValueError('packet_payload_contract')
        shutil.copyfile(read_dir/name,gen_dir/name)
        response=run(['-m','plm_l1_v010','generate','--model','model','--packet',name,'--order','reverse','--goals','object','subject'],gen_dir,out,f'GENERATE_{i}')
        generated=json.loads(response);target=parse(text);target['events'].reverse();target['goals']=['object','subject']
        if target['relation']!='unknown':target['relation']='after' if target['relation']=='before' else 'before'
        if parse(generated['text'])!=target:raise ValueError('isolated_semantic_mismatch')
        demos.append({'input_for_verifier_only':text,'output':generated['text'],'exact':True})
    run(['-m','plm_l1_v010','read','--model','model','--text','太郎が花子を助けた。その後、彼が花子を助けた。','--out','must-not-exist.json'],read_dir,out,'ATOMIC_ABSTAIN',expected=2)
    if (read_dir/'must-not-exist.json').exists():raise ValueError('partial_packet_emitted')
    ambiguity=[]
    target_meaning=data('evaluation')[0]['meaning'];target_meaning['events'][0]['polarity']='polarity:negative'
    for label in ('before','after'):
        shutil.copytree(ROOT/'results'/('ambiguity-'+label),gen_dir/('ambiguity-'+label))
        source=CommitteeModel.load(ROOT/'results'/('ambiguity-'+label));write(gen_dir/(label+'.json'),source.encode(target_meaning))
        response=run(['-m','plm_l1_v010','generate','--model','ambiguity-'+label,'--packet',label+'.json'],gen_dir,out,'AMBIGUITY_'+label,expected=2 if label=='before' else 0)
        row=json.loads(response);ambiguity.append({'stage':label,'status':row['status'],'reason':row.get('reason'),'text':row.get('text')})
    vend=vendor(out,a.legacy);manifest=check_manifest() if (ROOT/'RELEASE_MANIFEST.json').exists() else 'not_yet_packaged'
    report={'status':'passed','mode':a.mode,'source_freeze':freeze,'result_digest':claimed,'unit_tests':tests,'functional_comparison':comparison,
            'manifest_files':manifest,'vendor':vend,'isolated_training_without_reader_or_evaluator':True,'generation_without_reader_trainer_selector':True,
            'numeric_packet_only_transfer':True,'atomic_abstention':True,'whole_output_consensus':True,'demos':demos,'ambiguity_cli':ambiguity,
            'linux_execution_performed':False,'full_numeric_evaluation_rerun_by_this_command':False}
    write(out/'VERIFICATION.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
