"""Rerun comparison, SS-only requery isolation and saved-coefficient checks."""
import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.cases import dataset,fresh_observation
from evaluation.experiment import query
from ss_partial.runtime import PartialModel
from ss_retention.memory import CorrectionMemory
from ss_retention.runtime import complete

def copy_runtime(target):
    packages={'ss_retention':['__init__.py','context.py','memory.py','runtime.py','__main__.py'],
              'ss_partial':['__init__.py','contract.py','codec.py','runtime.py','update.py'],
              'ss_document':['__init__.py','contract.py','codec.py','runtime.py'],
              'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
              'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    for package,names in packages.items():
        p=target/package;p.mkdir(parents=True,exist_ok=True)
        for name in names:shutil.copy2(ROOT/package/name,p/name)
    shutil.copy2(ROOT/'verification/isolated_cli.py',target/'run.py')

def run(out,repeat=None):
    frozen=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False);index=read(ROOT/'results/INDEX.json');model=PartialModel.load(ROOT/'model')
    counts={'memories_loaded':0,'primary_requeries_compared':0,'reference_arrays_compared':0}
    repeated=None
    if repeat:
        hashes=lambda p:{x.relative_to(p).as_posix():sha(x) for x in p.rglob('*') if x.is_file() and x.name!='PERFORMANCE.json'}
        a,b=hashes(ROOT/'results'),hashes(Path(repeat));assert a==b,'full_repeat_differs'
        repeated=len(a);write(out/'REPEATABILITY.json',{'passed':True,'file_count':repeated,'files':a,'excluded':['PERFORMANCE.json']})
    data={s:read(ROOT/f'results/DATA-{s}.json') for s in (100,101)}
    assert all(data[s]==dataset(s) for s in data)
    with np.load(ROOT/'results/REFERENCE_SIGNALS.npz',allow_pickle=False) as z:
        expected_keys=set()
        for cid in index['conditions']:
            r=read(ROOT/'results/conditions'/(cid+'.json'));memory=CorrectionMemory.load(ROOT/'results/memories'/cid,model.codec.candidates)
            assert memory.fingerprint==r['memory_fingerprint'];counts['memories_loaded']+=1
            revised=CorrectionMemory.load(ROOT/'results/revised_memories'/cid,model.codec.candidates)
            assert revised.fingerprint==r['revised_fingerprint'];counts['memories_loaded']+=1
            focal=[c for c in data[r['data_seed']] if c['kind']=='focal']
            # First2 per saved condition: not a claim of a third complete evaluation.
            for i,c in enumerate(focal[:2]):
                actual=query(model,memory,c,('ambiguous','unobserved','unreadable')[i%3])
                assert actual==r['primary'][i];counts['primary_requeries_compared']+=1
            packet=model.encode(fresh_observation(focal[0],'ambiguous'));wanted={cid+'-initial':model.vector(packet)}
            done=complete(model,memory,focal[0]['episode'],packet)
            if 'packet' in done:wanted[cid+'-completed']=model.vector(done['packet'])
            for name,v in wanted.items():
                expected_keys.add(name);np.testing.assert_array_equal(v,z[name]);counts['reference_arrays_compared']+=1
        assert expected_keys==set(z.files)
    # Runtime folder receives fresh unobserved numeric inputs, not previously corrected packets.
    groot=out/'isolated';groot.mkdir();copy_runtime(groot);shutil.copytree(ROOT/'model',groot/'model')
    cid='d100-c0-b256-split_pair';shutil.copytree(ROOT/'results/memories'/cid,groot/'memory')
    memory=CorrectionMemory.load(groot/'memory',model.codec.candidates);isolated=[]
    for n in (2,3):
        c=next(c for c in data[100] if c['kind']=='focal' and c['known']['count']==n and c['target'].endswith('/subject'))
        p=model.encode(fresh_observation(c,'unobserved'));write(groot/f'packet{n}.json',p)
        cmd=[sys.executable,'-I','-B','-X','utf8','run.py','generate','--model','model','--memory','memory','--episode',c['episode'],'--packet',f'packet{n}.json','--order','reverse']
        proc=subprocess.run(cmd,cwd=groot,capture_output=True,text=True,encoding='utf-8');assert proc.returncode in (0,2),proc.stderr
        from ss_retention.runtime import generate
        actual=json.loads(proc.stdout);expected=generate(model,memory,c['episode'],p,'reverse');assert actual==expected
        isolated.append({'count':n,'case_id':c['id'],'command':cmd,'result':actual,'exit_code':proc.returncode,
                         'provenance':json.loads(proc.stderr),'fresh_unobserved_packet':True,'no_current_teacher_or_corrected_packet':True})
    write(out/'ISOLATED.json',isolated)
    manifest=None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        actual={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert actual==read(ROOT/'RELEASE_MANIFEST.json')['files'];manifest=len(actual)
    record={'passed':True,**counts,'full_repeat_equal_files':repeated,'isolated_queries':len(isolated),
            'isolated_generated':sum(r['result']['status']=='generated' for r in isolated),'manifest_files_checked':manifest,
            'frozen_source_digest':frozen,'eligible_for_inference':False}
    write(out/'VERIFY.json',record);print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--repeat');a=p.parse_args();run(a.out,a.repeat)
