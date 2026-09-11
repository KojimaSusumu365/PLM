import argparse,json,shutil,subprocess,sys
from pathlib import Path
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.guard_cases import build
from evaluation.experiment02 import prepare_inputs,trial,score
from ss_partial.runtime import PartialModel
from ss_core_v02.store import Store
from bridge.carrier import encode
from evaluate import summarize,acceptance

def hashes(folder):
    return {p.relative_to(folder).as_posix():sha(p) for p in Path(folder).rglob('*') if p.is_file()
            and p.name!='PERFORMANCE.json' and '__pycache__' not in p.parts}

def minimal(folder):
    packages={
        'ss_core_v02':['__init__.py','__main__.py','store.py','runtime.py'],
        'ss_core':['__init__.py','clock.py','memory.py','runtime.py'],
        'bridge':['__init__.py','carrier.py','recovery.py','runtime.py'],
        'ss_reconfirm':['__init__.py','session.py','runtime.py'],
        'ss_revision':['__init__.py','context.py','memory.py'],
        'ss_retention':['__init__.py','context.py','memory.py'],
        'ss_partial':['__init__.py','contract.py','codec.py','runtime.py','update.py'],
        'ss_document':['__init__.py','contract.py','codec.py','runtime.py'],
        'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
        'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    s='vendor/PLM-S1-v0.2';old=s+'/vendor/PLM-S1-v0.1';p=old+'/vendor/PLM-P1-v0.2'
    packages.update({s+'/plm_s1_v02':['__init__.py','link.py','receiver.py','packet.py'],
        old+'/plm_s1':['__init__.py','link.py'],p+'/plm_p1_v02':['__init__.py','recovery.py'],
        p+'/vendor/PLM-P1-v0.1/plm_p1':['__init__.py','core.py','packet.py']})
    for package,names in packages.items():
        (folder/package).mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copy2(ROOT/package/name,folder/package/name)
    shutil.copytree(ROOT/'model',folder/'model')
    shutil.copy2(ROOT/'verification/isolated_cli.py',folder/'run.py')

def run(out,repeat=None):
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False)
    assert build()==read(ROOT/'data/GUARD_CORPUS.json')
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,
                     capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and 'Ran 53 tests' in p.stderr,p.stderr
    write(out/'TESTS.json',{'passed':True,'tests':53,'stdout':p.stdout,'stderr':p.stderr})
    model=PartialModel.load(ROOT/'model');cases=read(ROOT/'data/GUARD_CORPUS.json')['splits']['evaluation'];by_id={c['id']:c for c in cases}
    packets,inputs=prepare_inputs(model,cases);assert inputs==read(ROOT/'results/INPUTS.json')
    rows=[];selected={};loaded=0
    index=read(ROOT/'results/INDEX.json')
    for name in index['runs']:
        r=read(ROOT/'results/runs'/name/'RESULT.json');rows.append(r)
        selected.setdefault((r['condition'],r['method']),(name,r))
        for stage in ('after','later'):
            s=Store.load(ROOT/'results/runs'/name/stage,model.codec.candidates)
            assert s.fingerprint==r[stage+'_fingerprint'];loaded+=1
        assert r['ss_memory_unchanged_on_hold']
        if loaded%200==0:print({'saved_stores_checked':loaded},flush=True)
    groups=summarize(rows);assert groups==read(ROOT/'results/SUMMARY.json')
    assert acceptance(groups,read(ROOT/'evaluation/PROTOCOL.json'))==read(ROOT/'results/DECISION.json')
    for i,(name,r) in enumerate(selected.values()):
        base=Store.load(ROOT/'results/bases'/str(r['seed']),model.codec.candidates)
        result=trial(model,base,cases,packets,by_id[r['case_id']],by_id[r['anchor_id']],r['seed'],r['condition'],r['method'],out/'replayed'/name)
        assert result==r, name
        for stage in ('after','later'):assert hashes(out/'replayed'/name/stage)==hashes(ROOT/'results/runs'/name/stage)
        if (i+1)%7==0:print({'full_trials_replayed':i+1},flush=True)
    old_cases={c['id']:c for c in read(ROOT/'data/CORPUS.json')['splits']['evaluation']}
    historical=read(ROOT/'results/HISTORICAL.json');old_replayed=0
    for r in historical:
        s=Store.load(ROOT/'results/historical'/r['store'],model.codec.candidates);assert s.fingerprint==r['fingerprint'];loaded+=1
        item=r['scores'][0];c=old_cases[item['case_id']]
        assert score(model,s,c,model.encode(c['query']))==item['result'];old_replayed+=1
    equal=None
    if repeat:
        assert hashes(ROOT/'results')==hashes(Path(repeat)),'full_repeat_mismatch'
        equal=len(hashes(ROOT/'results'))
        write(out/'REPEATABILITY.json',{'passed':True,'files':hashes(ROOT/'results'),'excluded':['PERFORMANCE.json']})
    isolated=[]
    for condition in ('clean','independent16'):
        name,r=selected[(condition,'guard')];c=by_id[r['case_id']];folder=out/('isolated-'+condition);folder.mkdir()
        minimal(folder);shutil.copytree(ROOT/'results/runs'/name/'later',folder/'store')
        write(folder/'scope.json',c['scope']);mid='isolated/'+condition
        write(folder/'wire.json',encode(model,packets[(c['id'],'query')],mid))
        p=subprocess.run([sys.executable,'-I','-B','-X','utf8','run.py','generate','--model','model','--memory','store',
            '--scope','scope.json','--wire','wire.json','--message-id',mid],cwd=folder,capture_output=True,text=True,encoding='utf-8')
        assert p.returncode in (0,2),p.stderr
        g=json.loads(p.stdout);provenance=json.loads(p.stderr)
        if r['later']['status']=='generated':assert g['status']=='generated' and g['text']==r['later']['outputs'][0]['generation']['text']
        else:assert g['status']=='needs_confirmation' and 'text' not in g
        isolated.append({'condition':condition,'result':g,'provenance':provenance})
    write(out/'ISOLATED.json',isolated)
    for name,item in read(ROOT/'verification/PREVIOUS.json')['copied'].items():assert sha(ROOT/name)==item['sha256'],name
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert actual==read(ROOT/'RELEASE_MANIFEST.json')['files'];manifest=len(actual)
    result={'passed':True,'frozen_digest':frozen,'tests':53,'saved_stores_loaded':loaded,'representative_full_trials_replayed':len(selected),
            'historical_saved_query_replays':old_replayed,'full_repeat_equal_files':equal,'input_receptions_regenerated':len(inputs),
            'isolated_generated':sum(r['result']['status']=='generated' for r in isolated),
            'isolated_pending_holds':sum(r['result']['status']=='needs_confirmation' for r in isolated),
            'manifest_files_checked':manifest,'primary_acceptance_passed':read(ROOT/'results/DECISION.json')['passed']}
    write(out/'VERIFY.json',result);print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--repeat');a=p.parse_args();run(a.out,a.repeat)
