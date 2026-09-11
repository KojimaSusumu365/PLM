import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from bridge.carrier import encode
from evaluation.integrity import ROOT,read,write,sha,verify
from evaluation.cases import build
from evaluation.experiment import inputs,train,query
from evaluation.channel import channel
from evaluate import summarize,acceptance

def hashes(folder):
    return {p.relative_to(folder).as_posix():sha(p) for p in Path(folder).rglob('*')
            if p.is_file() and p.name!='PERFORMANCE.json' and '__pycache__' not in p.parts}

def minimal(folder):
    packages = {
        'ss_core':['__init__.py','__main__.py','clock.py','memory.py','runtime.py'],
        'bridge':['__init__.py','carrier.py','recovery.py','runtime.py'],
        'ss_reconfirm':['__init__.py','session.py','runtime.py'],
        'ss_revision':['__init__.py','context.py','memory.py'],
        'ss_retention':['__init__.py','context.py','memory.py'],
        'ss_partial':['__init__.py','contract.py','codec.py','runtime.py','update.py'],
        'ss_document':['__init__.py','contract.py','codec.py','runtime.py'],
        'plm_l1_v09':['__init__.py','contract.py','codec.py','runtime.py','thresholds.py'],
        'plm_l1_v09/component':['__init__.py','runtime.py','algebra.py','lexicon.py','features.py','banked.py','projection.py']}
    s = 'vendor/PLM-S1-v0.2'
    old = s+'/vendor/PLM-S1-v0.1'
    p = old+'/vendor/PLM-P1-v0.2'
    packages.update({s+'/plm_s1_v02':['__init__.py','link.py','receiver.py','packet.py'],
                     old+'/plm_s1':['__init__.py','link.py'],p+'/plm_p1_v02':['__init__.py','recovery.py'],
                     p+'/vendor/PLM-P1-v0.1/plm_p1':['__init__.py','core.py','packet.py']})
    for package,names in packages.items():
        (folder/package).mkdir(parents=True,exist_ok=True)
        for name in names:
            shutil.copy2(ROOT/package/name,folder/package/name)
    shutil.copytree(ROOT/'model',folder/'model')
    shutil.copy2(ROOT/'verification/isolated_cli.py',folder/'run.py')

def run(out,repeat=None):
    frozen = verify()
    out = Path(out)
    out.mkdir(parents=True,exist_ok=False)
    data = read(ROOT/'data/CORPUS.json')
    assert build()==data, 'corpus_regeneration'
    p = subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,
                       capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and 'Ran 30 tests' in p.stderr,p.stderr
    write(out/'TESTS.json',{'passed':True,'stdout':p.stdout,'stderr':p.stderr})
    rows = read(ROOT/'results/ROWS.json')
    groups = summarize(rows)
    assert groups==read(ROOT/'results/SUMMARY.json')
    assert acceptance(groups,read(ROOT/'results/NUMERICAL.json'),read(ROOT/'results/PAIRED.json'),
                      read(ROOT/'results/UPDATE_FAULTS.json'),read(ROOT/'results/INPUTS.json'),
                      read(ROOT/'evaluation/PROTOCOL.json'))==read(ROOT/'results/DECISION.json')
    model = PartialModel.load(ROOT/'model')
    cases = data['splits']['evaluation']
    by_id = {c['id']:c for c in cases}
    packets,record = inputs(model,cases,'evaluation')
    assert record==read(ROOT/'results/INPUTS.json')
    memories = {}
    for item in read(ROOT/'results/INDEX.json')['memories']:
        memory = RevisionMemory.load(ROOT/'results/runs'/item['id']/'memory',model.codec.candidates)
        assert memory.fingerprint==item['memory_fingerprint']
        # Cache bytes depend on operations since load; compare learned quantities explicitly.
        assert memory.cost()['total_coefficient_bytes']==item['cost']['total_coefficient_bytes']
        assert memory.cost()['confirmed_targets']==2*item['learned_documents'] and memory.cost()['root_count']==item['learned_documents']
        memories[(item['seed'],item['mode'])] = memory
    selected = {}
    for row in rows:
        selected.setdefault((row['mode'],row['condition']),row)
    for row in selected.values():
        memory = memories[(row['seed'],row['mode'])]
        condition = row['condition']
        if condition=='coefficients_zero':
            memory = copy.deepcopy(memory)
            for part in memory.ss.parts.values():
                part.weights[:] = 0
        expected = query(model,memory,by_id[row['case_id']],packets[(row['case_id'],'query')],row['mode'],row['seed'],
                         None if condition in ('main','coefficients_zero') else condition)
        expected['condition'] = condition
        assert expected==row, (row['mode'],condition)
    # One complete teacher-sequence replay, in addition to all-run external repeat comparison.
    memory,receipts = train(model,cases,packets,0,'stream1',out/'replayed/0-stream1')
    assert receipts==read(ROOT/'results/runs/0-stream1/TEACHERS.json')
    assert hashes(out/'replayed/0-stream1/memory')==hashes(ROOT/'results/runs/0-stream1/memory')
    repeated = None
    if repeat:
        assert hashes(ROOT/'results')==hashes(Path(repeat)), 'full_repeat_mismatch'
        repeated = len(hashes(ROOT/'results'))
        write(out/'REPEATABILITY.json',{'passed':True,'files':hashes(ROOT/'results'),'excluded':['PERFORMANCE.json']})
    isolated = []
    focal = [c for c in cases if c['kind']=='focal']
    for i in (0,4):
        case = focal[i]
        folder = out/f'isolated-{i}'
        folder.mkdir()
        minimal(folder)
        shutil.copytree(ROOT/'results/runs/0-stream1/memory',folder/'memory')
        write(folder/'scope.json',case['scope'])
        mid = 'ss-core01/'+case['id']+'/query'
        seed = 41000+cases.index(case)*97+10000
        wire,_ = channel(model,encode(model,model.encode(case['query']),mid),'partial25',seed)
        write(folder/'received.json',wire)
        p = subprocess.run([sys.executable,'-I','-B','-X','utf8','run.py','generate','--model','model','--memory','memory',
                            '--scope','scope.json','--wire','received.json','--message-id',mid],cwd=folder,
                           capture_output=True,text=True,encoding='utf-8')
        assert p.returncode==0,p.stderr
        g,provenance = json.loads(p.stdout),json.loads(p.stderr)
        expected = next(r for r in rows if r['case_id']==case['id'] and r['seed']==0 and r['mode']=='stream1' and r['condition']=='main')
        assert g['status']=='generated' and g['text']==expected['result']['outputs'][0]['generation']['text']
        assert g['fresh_session_no_receipts']
        isolated.append({'case_id':case['id'],'result':g,'provenance':provenance})
    write(out/'ISOLATED.json',isolated)
    manifest_count = None
    if (ROOT/'RELEASE_MANIFEST.json').exists():
        actual = {p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='RELEASE_MANIFEST.json'}
        assert actual==read(ROOT/'RELEASE_MANIFEST.json')['files']
        manifest_count = len(actual)
    result = {'passed':True,'frozen_digest':frozen,'tests':30,'saved_memories_loaded':len(memories),
              'representative_queries_replayed':len(selected),'full_teacher_sequences_replayed':1,
              'full_repeat_equal_files':repeated,'input_wires_and_receptions_regenerated':len(record),
              'isolated_generations':len(isolated),'corpus_rebuilt_exactly':True,'summaries_recomputed':True,
              'manifest_files_checked':manifest_count,'numerical_acceptance_passed':read(ROOT/'results/DECISION.json')['passed']}
    write(out/'VERIFY.json',result)
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out',required=True)
    p.add_argument('--repeat')
    a = p.parse_args()
    run(a.out,a.repeat)
