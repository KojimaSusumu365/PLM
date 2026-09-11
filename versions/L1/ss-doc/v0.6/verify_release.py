import argparse,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.delay_cases import build,audit,entries
from evaluation.delay_experiment import background,slot_score,run_selection
from evaluation.reconfirm_experiment import probe
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_select.memory import SelectorMemory
from ss_select.runtime import Workset,choose
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import generate

def hashes(p):return {x.relative_to(p).as_posix():sha(x) for x in p.rglob('*') if x.is_file() and x.name!='PERFORMANCE.json'}

def copy_runtime(folder):
    packages={'ss_select':['__init__.py','features.py','memory.py','runtime.py','__main__.py'],
       'ss_reconfirm':['__init__.py','session.py','runtime.py','__main__.py'],'ss_revision':['__init__.py','context.py','memory.py'],
       'ss_retention':['__init__.py','context.py','memory.py'],'ss_partial':['__init__.py','contract.py','codec.py','runtime.py','update.py'],
       'ss_document':['__init__.py','contract.py','codec.py','runtime.py'],'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
       'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    for package,names in packages.items():
        p=folder/package;p.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copy2(ROOT/package/name,p/name)
    shutil.copy2(ROOT/'verification/isolated_cli.py',folder/'run.py')

def run(out,repeat=None,retrained=None):
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False);data=read(ROOT/'data/DELAY_DATASETS.json');exclusions=read(ROOT/'data/DELAY_EXCLUSIONS.json')
    assert build(exclusions)==data and audit(data,exclusions)==read(ROOT/'verification/DATA_AUDIT.json')
    repeated=trained=None
    if repeat:
        h=hashes(ROOT/'results');assert h==hashes(Path(repeat));repeated=len(h);write(out/'REPEATABILITY.json',{'passed':True,'file_count':repeated,'files':h,'excluded':['PERFORMANCE.json']})
    if retrained:
        h=hashes(ROOT/'training_results');assert h==hashes(Path(retrained));trained=len(h)
        assert hashes(ROOT/'data/selector_model')==hashes(Path(retrained)/'model')
        write(out/'SELECTOR_RETRAINING.json',{'passed':True,'file_count':trained,'files':h,'excluded':['PERFORMANCE.json']})
    model=PartialModel.load(ROOT/'model');selector=SelectorMemory.load(ROOT/'data/selector_model');plan=read(ROOT/'evaluation/PROTOCOL.json');index=read(ROOT/'results/INDEX.json')
    counts={'base_memories_loaded':0,'after_answers_memories_loaded':0,'final_memories_loaded':0,'selection_rounds_replayed':0,'external_answers_replayed':0,
            'delayed_fresh_probes_compared':0,'reference_arrays_compared':0};keys=set()
    for bid in index['bases']:
        m=RevisionMemory.load(ROOT/'results/base_memories'/bid,model.codec.candidates);assert m.fingerprint==read(ROOT/'results/baselines'/(bid+'.json'))['memory_fingerprint'];counts['base_memories_loaded']+=1
    with np.load(ROOT/'results/REFERENCE_SIGNALS.npz',allow_pickle=False) as z:
        for cid in index['conditions']:
            r=read(ROOT/'results/conditions'/(cid+'.json'));ds=data['splits'][r['split']];focal=[ds['cases'][i] for i in ds['order']]
            records=read(ROOT/f"results/TEACHERS-{r['split']}.json");memory=RevisionMemory.load(ROOT/'results/base_memories'/r['base'],model.codec.candidates)
            trace=run_selection(model,memory,focal,r['policy'],selector,plan['exact_confirmation_budget'],r['base']);assert trace==r['trace']
            counts['selection_rounds_replayed']+=1;counts['external_answers_replayed']+=len(trace)
            assert slot_score(memory,focal,records)==r['immediate']
            saved=RevisionMemory.load(ROOT/'results/after_answers_memories'/cid,model.codec.candidates);assert saved.fingerprint==memory.fingerprint==r['after_answers_fingerprint'];counts['after_answers_memories_loaded']+=1
            background(memory,records,r['load'],r['load']+plan['delayed_background'])
            final=RevisionMemory.load(ROOT/'results/memories'/cid,model.codec.candidates);assert final.fingerprint==memory.fingerprint==r['memory_fingerprint'];counts['final_memories_loaded']+=1
            assert slot_score(final,focal,records)==r['delayed_slots']
            row,source,completed=probe(model,final,focal[0]);assert row==r['delayed'][0];counts['delayed_fresh_probes_compared']+=1
            arrays={cid+'-initial':model.vector(source)}
            if completed is not None:arrays[cid+'-completed']=model.vector(completed)
            for name,v in arrays.items():np.testing.assert_array_equal(v,z[name]);keys.add(name);counts['reference_arrays_compared']+=1
        assert keys==set(z.files)
    folder=out/'isolated';folder.mkdir();copy_runtime(folder);shutil.copytree(ROOT/'model',folder/'model');shutil.copytree(ROOT/'data/selector_model',folder/'selector')
    bid='d400-c0-versioned_shared-l64';cid=bid+'-ss_learned';shutil.copytree(ROOT/'results/base_memories'/bid,folder/'base');shutil.copytree(ROOT/'results/memories'/cid,folder/'memory')
    ds=data['splits']['400'];focal=[ds['cases'][i] for i in ds['order']];work=entries(model,focal);write(folder/'workset.json',work)
    def call(args):
        p=subprocess.run([sys.executable,'-I','-B','-X','utf8','run.py',*args],cwd=folder,capture_output=True,text=True,encoding='utf-8')
        assert p.returncode in (0,2),p.stderr;return {'result':json.loads(p.stdout),'provenance':json.loads(p.stderr),'exit_code':p.returncode}
    selected=call(['ss_select','choose','--model','model','--memory','base','--workset','workset.json','--selector','selector','--seed',bid])
    m=RevisionMemory.load(folder/'base',model.codec.candidates);assert selected['result']==choose(m,Workset(model,work),selector=selector,seed=bid)
    final=RevisionMemory.load(folder/'memory',model.codec.candidates);generated=[]
    for n in (2,3):
        c=next(c for c in ds['cases'] if c['kind']=='focal' and c['final']['count']==n);e=next(e for e in work if e['id']==c['id'])
        write(folder/f'packet{n}.json',e['packet']);write(folder/f'scope{n}.json',e['scope'])
        call(['ss_reconfirm','start','--model','model','--memory','memory','--packet',f'packet{n}.json','--scope',f'scope{n}.json','--out',f'session{n}.json'])
        assert read(folder/f'session{n}.json')['payload']['confirmed']=={}
        r=call(['ss_reconfirm','generate','--model','model','--memory','memory','--session',f'session{n}.json','--order','reverse'])
        assert r['result']==generate(model,final,Session(model,final,e['scope'],e['packet']),order='reverse')
        generated.append({'count':n,'case_id':c['id'],**r,'no_session_receipts':True})
    write(out/'ISOLATED.json',{'selection':selected,'generation':generated,'teacher_absent':True})
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert actual==read(ROOT/'RELEASE_MANIFEST.json')['files'];manifest=len(actual)
    record={'passed':True,**counts,'datasets_rebuilt_exactly':True,'full_repeat_equal_files':repeated,'selector_retraining_equal_files':trained,
            'isolated_selection':True,'isolated_generated':sum(r['result']['status']=='generated' for r in generated),'isolated_generation_queries':2,
            'manifest_files_checked':manifest,'frozen_digest':frozen,'eligible_for_inference':False}
    write(out/'VERIFY.json',record);print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--repeat');p.add_argument('--retrained');a=p.parse_args();run(a.out,a.repeat,a.retrained)
