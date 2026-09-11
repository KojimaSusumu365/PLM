import argparse,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.revision_cases import cases,fresh
from evaluation.revision_experiment import query
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_revision.runtime import complete,generate

def copy_runtime(target):
    packages={'ss_revision':['__init__.py','context.py','memory.py','runtime.py','__main__.py'],
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
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False);model=PartialModel.load(ROOT/'model')
    repeated=None
    if repeat:
        hashes=lambda p:{f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file() and f.name!='PERFORMANCE.json'}
        original=hashes(ROOT/'results');assert original==hashes(Path(repeat)),'full_repeat_differs'
        repeated=len(original);write(out/'REPEATABILITY.json',{'passed':True,'file_count':repeated,'files':original,'excluded':['PERFORMANCE.json']})
    data={s:read(ROOT/f'results/DATA-{s}.json') for s in (200,201)};assert all(data[s]==cases(s) for s in data)
    count={'memories_loaded':0,'primary_requeries_compared':0,'reference_arrays_compared':0};keys=set()
    with np.load(ROOT/'results/REFERENCE_SIGNALS.npz',allow_pickle=False) as z:
        for cid in read(ROOT/'results/INDEX.json')['conditions']:
            r=read(ROOT/'results/conditions'/(cid+'.json'));m=RevisionMemory.load(ROOT/'results/memories'/cid,model.codec.candidates)
            assert m.fingerprint==r['memory_fingerprint'];count['memories_loaded']+=1
            before=RevisionMemory.load(ROOT/'results/before_background'/cid,model.codec.candidates);count['memories_loaded']+=1
            focal=data[r['data_seed']][:24]
            for i,c in enumerate(focal[:2]):
                assert query(model,m,c,mode=('missing','ambiguous','mixed')[i%3])==r['primary'][i];count['primary_requeries_compared']+=1
            p=model.encode(fresh(focal[0]));wanted={cid+'-initial':model.vector(p)};done=complete(model,m,focal[0]['scope'],p)
            if 'packet' in done:wanted[cid+'-completed']=model.vector(done['packet'])
            for name,v in wanted.items():np.testing.assert_array_equal(v,z[name]);keys.add(name);count['reference_arrays_compared']+=1
            if 'protected' in m.ss.parts:np.testing.assert_array_equal(before.ss.parts['protected'].weights,m.ss.parts['protected'].weights)
        assert keys==set(z.files)
    isolated=[];folder=out/'isolated';folder.mkdir();copy_runtime(folder);shutil.copytree(ROOT/'model',folder/'model')
    # Low-load fixed selection, not cherry-picked after inspecting high-load primary outcomes.
    cid='d200-c0-b64-versioned_pair';shutil.copytree(ROOT/'results/memories'/cid,folder/'memory')
    m=RevisionMemory.load(folder/'memory',model.codec.candidates)
    for n,c in zip((2,3),data[200][:2]):
        p=model.encode(fresh(c));write(folder/f'packet{n}.json',p);write(folder/f'scope{n}.json',c['scope'])
        cmd=[sys.executable,'-I','-B','-X','utf8','run.py','generate','--model','model','--memory','memory','--scope',f'scope{n}.json','--packet',f'packet{n}.json','--order','reverse']
        proc=subprocess.run(cmd,cwd=folder,capture_output=True,text=True,encoding='utf-8');assert proc.returncode in (0,2),proc.stderr
        actual=json.loads(proc.stdout);assert actual==generate(model,m,c['scope'],p,'reverse')
        isolated.append({'count':n,'case_id':c['id'],'result':actual,'exit_code':proc.returncode,'provenance':json.loads(proc.stderr),
                         'two_values_unobserved':True,'current_teacher_and_completed_packet_absent':True})
    write(out/'ISOLATED.json',isolated)
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert actual==read(ROOT/'RELEASE_MANIFEST.json')['files'];manifest=len(actual)
    record={'passed':True,**count,'full_repeat_equal_files':repeated,'isolated_generated':sum(r['result']['status']=='generated' for r in isolated),
            'isolated_queries':2,'manifest_files_checked':manifest,'frozen_digest':frozen,'eligible_for_inference':False}
    write(out/'VERIFY.json',record);print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--repeat');a=p.parse_args();run(a.out,a.repeat)
