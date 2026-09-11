import argparse,importlib.util,json,platform,statistics,subprocess,sys,time
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
from evaluation.revision_cases import cases
from evaluation.cases import scene_key
from ss_partial.contract import to_meaning
from ss_partial.runtime import PartialModel
from ss_revision.memory import RevisionMemory
from ss_revision.runtime import generate

def run(work,verified):
    verify();work=Path(work);work.mkdir(parents=True,exist_ok=False);verified=Path(verified)
    for src,dst in (('VERIFY.json','RELEASE_VERIFY.json'),('REPEATABILITY.json','REPEATABILITY.json'),('ISOLATED.json','ISOLATED.json')):write(ROOT/'verification'/dst,read(verified/src))
    spec=importlib.util.spec_from_file_location('revision_demo',ROOT/'examples/demo.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    example=module.demo(ROOT/'examples/run');model=PartialModel.load(ROOT/'model');m=RevisionMemory.load(ROOT/'examples/run/memory',model.codec.candidates)
    packet=read(ROOT/'examples/run/fresh-packet.json');scope=example['scope'];times=[];fp=m.fingerprint
    for _ in range(8):
        start=time.perf_counter();g=generate(model,m,scope,packet,'reverse');times.append(time.perf_counter()-start)
        assert g['text']==example['after_restart']['text']
    assert m.fingerprint==fp;m.save(work/'after_inference');model.save(work/'language_after_inference')
    hashes=lambda p:{x.relative_to(p).as_posix():sha(x) for x in p.rglob('*') if x.is_file()}
    assert hashes(work/'after_inference')==hashes(ROOT/'examples/run/memory') and hashes(work/'language_after_inference')==hashes(ROOT/'model')
    prior=read(ROOT/'verification/PREVIOUS_BASELINE.json');old=ROOT.parent/prior['release']
    assert hashes(old)==prior['files'] and sha(old.with_name(old.name+'.zip'))==prior['zip_sha256']
    assert all(sha(ROOT/k)==v for k,v in prior['copied_files'].items())
    write(ROOT/'verification/PRESERVATION.json',{'passed':True,'previous_files_unchanged':len(prior['files']),'previous_zip_sha256':prior['zip_sha256'],
          'copied_files_unchanged':len(prior['copied_files']),'language_model_unchanged':True,'revision_weights_unchanged_during_inference':True})
    sets=[];members=[];initial_sets=[];focal_sets=[]
    for seed,dev in (('development',True),(200,False),(201,False)):
        ds=cases(seed,dev);membership=defaultdict(list);initial_set=set();focal_set=set()
        for c in ds:
            initial_set.add(scene_key(to_meaning(c['initial'],model.codec.candidates)))
            for stage,o in enumerate([c['initial']]+[s['known'] for s in c['steps']]):
                k=scene_key(to_meaning(o,model.codec.candidates));membership[k].append({'id':c['id'],'kind':c['kind'],'stage':stage})
                if c['kind']=='focal':focal_set.add(k)
        sets.append(set(membership));members.append(membership);initial_sets.append(initial_set);focal_sets.append(focal_set)
    overlaps=[{'sets':[i,j],'scenes':[{'left':members[i][k],'right':members[j][k]} for k in sorted(sets[i]&sets[j])]} for i in range(3) for j in range(i+1,3)]
    dev_disjoint=not (sets[0]&sets[1] or sets[0]&sets[2]);assert dev_disjoint
    strict_disjoint=not any(sets[i]&sets[j] for i in range(3) for j in range(i+1,3))
    data=cases(200)+cases(201);assert len({c['scope']['episode'] for c in data})==560
    write(ROOT/'verification/DATA_AUDIT.json',{'completed':True,'passed':strict_disjoint,'focal_scenes':48,'background_scenes':512,'all_560_episode_ids_unique':True,
          'strict_all_revision_scene_disjointness':strict_disjoint,'development_eval_disjoint':dev_disjoint,
          'initial_evaluation_scene_overlap':len(initial_sets[1]&initial_sets[2]),'focal_evaluation_scene_overlap':len(focal_sets[1]&focal_sets[2]),
          'revision_scene_counts':list(map(len,sets)),'overlaps':overlaps,
          'note':'One evaluation-focal / other-evaluation-background coarse scene overlap is retained and disclosed,not removed after observing outcomes. Scene signature ignores event order and temporal edges;each dataset uses independently initialized memories.'})
    write(ROOT/'verification/BENCHMARK.json',{'seconds':times[1:],'median_seconds':statistics.median(times[1:]),'memory_cost':m.cost(),
          'partial_document_basis_bytes':model.codec.storage()['total_document_basis_bytes'],'generator_document_basis_bytes':model.document.codec.storage()['document_basis_bytes'],
          'scope':'Three-event two-hole demo;7 warm serial repetitions after1 warmup;no load/teacher latency,totalRSS,power,or hardware-isolated performance comparison.'})
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()})
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
    write(ROOT/'verification/FINAL_TESTS.json',{'passed':True,'stdout':p.stdout,'stderr':p.stderr})
    cmd=[sys.executable,'-B','-m','ss_revision','generate','--model','model','--memory','examples/run/memory','--scope','examples/run/scope.json','--packet','examples/run/fresh-packet.json','--order','reverse']
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
    assert json.loads(p.stdout)['text']==example['after_restart']['text']
    write(ROOT/'verification/CLI.json',{'command':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    print({'passed':True,'demo':example['after_restart']['text']},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);p.add_argument('--verified',required=True);a=p.parse_args();run(a.work,a.verified)
