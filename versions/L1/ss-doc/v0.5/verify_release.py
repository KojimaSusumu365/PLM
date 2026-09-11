import argparse,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.reconfirm_cases import build,audit_datasets,observation
from evaluation.reconfirm_experiment import episode,probe
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate

def copy_runtime(target):
    packages={'ss_reconfirm':['__init__.py','session.py','runtime.py','__main__.py'],
              'ss_revision':['__init__.py','context.py','memory.py'],
              'ss_retention':['__init__.py','context.py','memory.py'],
              'ss_partial':['__init__.py','contract.py','codec.py','runtime.py','update.py'],
              'ss_document':['__init__.py','contract.py','codec.py','runtime.py'],
              'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
              'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    for package,names in packages.items():
        p=target/package;p.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copy2(ROOT/package/name,p/name)
    shutil.copy2(ROOT/'verification/isolated_cli.py',target/'run.py')

def run(out,repeat=None):
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    data=read(ROOT/'data/RECONFIRM_DATASETS.json');exclude=read(ROOT/'data/SPLIT_EXCLUSIONS.json');assert build(exclude)==data
    assert audit_datasets(data,exclude)==read(ROOT/'verification/DATA_AUDIT.json')
    model=PartialModel.load(ROOT/'model');index=read(ROOT/'results/INDEX.json');repeated=None
    if repeat:
        hashes=lambda p:{f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file() and f.name!='PERFORMANCE.json'}
        first=hashes(ROOT/'results');assert first==hashes(Path(repeat)),'full_repeat_differs';repeated=len(first)
        write(out/'REPEATABILITY.json',{'passed':True,'file_count':repeated,'files':first,'excluded':['PERFORMANCE.json']})
    counts={'base_memories_loaded':0,'final_memories_loaded':0,'closed_loop_prefix_episodes_compared':0,'cold_probes_compared':0,'reference_arrays_compared':0}
    for base in index['bases']:
        m=RevisionMemory.load(ROOT/'results/base_memories'/base,model.codec.candidates)
        assert m.fingerprint==read(ROOT/'results/baselines'/(base+'.json'))['memory_fingerprint'];counts['base_memories_loaded']+=1
    keys=set()
    with np.load(ROOT/'results/REFERENCE_SIGNALS.npz',allow_pickle=False) as z:
        for cid in index['conditions']:
            r=read(ROOT/'results/conditions'/(cid+'.json'));ds=data['splits'][r['split']];ordered=[ds['cases'][i] for i in ds['query_order']]
            base=RevisionMemory.load(ROOT/'results/base_memories'/r['base'],model.codec.candidates);used=0
            for i,c in enumerate(ordered[:2]):
                actual=episode(model,base,c,r['policy'],r['budget_cap']-used);used+=actual['confirmations_used']
                assert actual==r['primary'][i];counts['closed_loop_prefix_episodes_compared']+=1
            final=RevisionMemory.load(ROOT/'results/memories'/cid,model.codec.candidates);assert final.fingerprint==r['memory_fingerprint'];counts['final_memories_loaded']+=1
            for i,c in enumerate(ordered[:2]):
                row,source,completed=probe(model,final,c);assert row==r['cold'][i];counts['cold_probes_compared']+=1
                if i==0:
                    wanted={cid+'-initial':model.vector(source)}
                    if completed is not None:wanted[cid+'-completed']=model.vector(completed)
                    for name,v in wanted.items():np.testing.assert_array_equal(v,z[name]);keys.add(name);counts['reference_arrays_compared']+=1
        assert keys==set(z.files)
    folder=out/'isolated';folder.mkdir();copy_runtime(folder);shutil.copytree(ROOT/'model',folder/'model')
    cid='d300-c0-versioned_shared-ss_selective-b24';shutil.copytree(ROOT/'results/memories'/cid,folder/'memory')
    final=RevisionMemory.load(folder/'memory',model.codec.candidates);isolated=[]
    for n in (2,3):
        # Fixed first case of each length, chosen by schema not by success.
        c=next(c for c in data['splits']['300']['cases'] if c['kind']=='focal' and c['final']['count']==n)
        p=model.encode(observation(c,'missing'));write(folder/f'packet{n}.json',p);write(folder/f'scope{n}.json',c['scope'])
        start=[sys.executable,'-I','-B','-X','utf8','run.py','start','--model','model','--memory','memory','--scope',f'scope{n}.json','--packet',f'packet{n}.json','--out',f'session{n}.json']
        proc=subprocess.run(start,cwd=folder,capture_output=True,text=True,encoding='utf-8');assert proc.returncode==0,proc.stderr
        payload=read(folder/f'session{n}.json')['payload'];assert payload['confirmed']=={}
        cmd=[sys.executable,'-I','-B','-X','utf8','run.py','generate','--model','model','--memory','memory','--session',f'session{n}.json','--order','reverse']
        proc=subprocess.run(cmd,cwd=folder,capture_output=True,text=True,encoding='utf-8');assert proc.returncode in (0,2),proc.stderr
        actual=json.loads(proc.stdout);assert actual==generate(model,final,Session(model,final,c['scope'],p),order='reverse')
        isolated.append({'count':n,'case_id':c['id'],'result':actual,'provenance':json.loads(proc.stderr),'exit_code':proc.returncode,
                         'fresh_session_receipts_empty':True,'both_values_unobserved':True,'teacher_absent':True})
    write(out/'ISOLATED.json',isolated)
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert actual==read(ROOT/'RELEASE_MANIFEST.json')['files'];manifest=len(actual)
    record={'passed':True,**counts,'datasets_rebuilt_exactly':True,'full_repeat_equal_files':repeated,'isolated_queries':2,
            'isolated_generated':sum(r['result']['status']=='generated' for r in isolated),'manifest_files_checked':manifest,
            'frozen_digest':frozen,'eligible_for_inference':False}
    write(out/'VERIFY.json',record);print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--repeat');a=p.parse_args();run(a.out,a.repeat)
