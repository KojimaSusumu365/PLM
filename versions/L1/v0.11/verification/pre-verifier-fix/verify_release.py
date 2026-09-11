import argparse,json,os,re,shutil,subprocess,sys,tempfile,zipfile,hashlib
from pathlib import Path
from plm_l1_v011.core import Model,observe
from plm_l1_v011.portability import compare
from plm_l1_v011.algebra import digest
from evaluation.integrity import ROOT,verify_freeze,manifest,sha
from evaluation.tasks import semantic_queries
from evaluate import judge
V010_SHA='00f2265ab4c8af2d827e3da4320f0adeff0dca3d8271cac0ba3a53f1a18967d8'

def write(p,x):
    with Path(p).open('x',encoding='utf-8') as f:f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def run(args,cwd,out,label,expected=0):
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1');env.pop('PYTHONPATH',None)
    r=subprocess.run([sys.executable,'-B',*args],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',timeout=900)
    (out/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
    if r.returncode!=expected:raise ValueError(label+': '+(r.stdout+r.stderr)[-5000:])
    return r.stdout
def copy_package(target,exclude=()):
    for p in (ROOT/'plm_l1_v011').glob('*.py'):
        if p.name in exclude:continue
        dest=target/'plm_l1_v011'/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--mode',choices=('strict','functional'),default='strict');a=p.parse_args()
    out=Path(a.out).resolve()
    if out.is_relative_to(ROOT):raise ValueError('verification_output_must_be_outside_release')
    out.mkdir(parents=True,exist_ok=False);freeze=verify_freeze()
    r=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'));claimed=r.pop('result_digest')
    if digest(r)!=claimed or r['freeze_hash']!=freeze or judge(r)!=r['checks'] or not r['all_checks_passed']:raise ValueError('evaluation_integrity_failure')
    log=run(['-m','unittest','discover','-s','tests','-v'],ROOT,out,'UNIT_TESTS');n=int(re.search(r'Ran (\d+) tests',log).group(1))
    tasks={t['id']:t for t in json.loads((ROOT/'data/evaluation.json').read_text(encoding='utf-8'))};comparisons={}
    train_dir=out/'training-only';copy_package(train_dir)
    guard="from pathlib import Path; import importlib.util; assert importlib.util.find_spec('evaluation') is None; assert not Path('vendor').exists(); assert not Path('results').exists(); print('No evaluation, oracle, vendor or old weights')"
    run(['-c',guard],train_dir,out,'TRAIN_BOUNDARY')
    for name,record in r['saved_models'].items():
        task=tasks[record['task_id']];source=Model.load(ROOT/'results'/name)
        if source.fingerprint!=record['fingerprint']:raise ValueError('saved_model_result_mismatch')
        for field,rows in (('train',task['train']+(task['added'] if record['after'] else [])),('selection',task['selection']),('calibration',task['calibration'])):write(train_dir/(name+'-'+field+'.json'),rows)
        run(['-m','plm_l1_v011','train','--train',name+'-train.json','--selection',name+'-selection.json','--calibration',name+'-calibration.json','--representation',source.config['representation'],'--selector',source.config['selector'],'--dimension',str(source.config['requested_dimension']),'--seed',source.config['seed'],'--out',name],train_dir,out,'TRAIN_'+name)
        candidate=Model.load(train_dir/name);contexts=[row['context'] for row in task['test']]+[q['context'] for q in semantic_queries(task)]
        result=compare(source,candidate,contexts)
        if not result['functional_passed'] or (a.mode=='strict' and not result['strict_fingerprint_equal']):raise ValueError('isolated_refit_mismatch')
        comparisons[name]=result
    decoder=out/'decoder-only';copy_package(decoder,{'training.py'});shutil.copytree(ROOT/'results/roles',decoder/'model')
    run(['-c',"import importlib.util; from pathlib import Path; assert importlib.util.find_spec('plm_l1_v011.training') is None; assert importlib.util.find_spec('evaluation') is None; assert not Path('train.json').exists(); print('Numeric decoder without trainer, selection, corpus or evaluator')"],decoder,out,'DECODER_BOUNDARY')
    model=Model.load(ROOT/'results/roles');role_task=tasks[r['saved_models']['roles']['task_id']];packet=model.encode(role_task['test'][0]['context'])
    demos=[]
    for fraction in (1.,.5,0.):
        observed=observe(packet,fraction,'isolated-mask');write(decoder/(str(fraction)+'.json'),observed)
        expected=model.decode(observed);actual=json.loads(run(['-m','plm_l1_v011','decode','--model','model','--input',str(fraction)+'.json'],decoder,out,'DECODE_'+str(fraction),0 if expected['value'] is not None else 2))
        if actual!=expected:raise ValueError('isolated_decode_mismatch')
        demos.append({'fraction':fraction,'status':actual['status'],'value':actual['value'],'expected_truth':role_task['test'][0]['label']})
    bad=dict(packet,raw_text='must-not-be-used');write(decoder/'bad.json',bad)
    run(['-m','plm_l1_v011','decode','--model','model','--input','bad.json'],decoder,out,'INVALID_PACKET',2)
    old=ROOT/'vendor/PLM-L1-v0.10.zip'
    if sha(old)!=V010_SHA:raise ValueError('vendor_hash_mismatch')
    with zipfile.ZipFile(old) as z:
        if z.testzip() is not None:raise ValueError('vendor_crc_failure')
        prefix='PLM-L1-v0.10/';expected=json.loads(z.read(prefix+'RELEASE_MANIFEST.json'))['files']
        actual={i.filename[len(prefix):]:hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir() and i.filename!=prefix+'RELEASE_MANIFEST.json'}
        if expected!=actual:raise ValueError('vendor_inventory_mismatch')
    count=manifest() if (ROOT/'RELEASE_MANIFEST.json').exists() else 'not_yet_packaged'
    report={'status':'passed','mode':a.mode,'unit_tests':n,'source_freeze':freeze,'result_digest':claimed,'saved_model_comparisons':comparisons,
            'isolated_training_without_evaluator':True,'numeric_only_decoder_without_trainer':True,'numeric_demos':demos,'manifest_files':count,
            'vendor':{'v010_sha256':V010_SHA,'crc_valid':True,'manifest_files':len(expected)},'linux_execution_performed':False,
            'v010_overabstention_policy_changed':False,'p1_s1_integration_performed':False,'full_numeric_evaluation_rerun_by_this_command':False}
    write(out/'VERIFICATION.json',report);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
