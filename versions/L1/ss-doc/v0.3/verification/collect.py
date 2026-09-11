import argparse
import importlib.util
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
from evaluation.cases import dataset,scene_key
from ss_partial.runtime import PartialModel
from ss_retention.memory import CorrectionMemory
from ss_retention.runtime import generate

def main(work,verified):
    verify();work=Path(work);work.mkdir(parents=True,exist_ok=False);verified=Path(verified)
    for src,dst in (('VERIFY.json','RELEASE_VERIFY.json'),('REPEATABILITY.json','REPEATABILITY.json'),('ISOLATED.json','ISOLATED.json')):write(ROOT/'verification'/dst,read(verified/src))
    spec=importlib.util.spec_from_file_location('retention_demo',ROOT/'examples/demo.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    example=module.demo(ROOT/'examples/run');assert example['after_restart']['status']=='generated'
    model=PartialModel.load(ROOT/'model');memory=CorrectionMemory.load(ROOT/'examples/run/memory',model.codec.candidates)
    packet=read(ROOT/'examples/run/fresh-packet.json');fp=memory.fingerprint;times=[]
    for _ in range(8):
        start=time.perf_counter();result=generate(model,memory,example['episode'],packet,'reverse');times.append(time.perf_counter()-start)
        assert result['text']==example['after_restart']['text']
    assert memory.fingerprint==fp;memory.save(work/'memory_after_inference');model.save(work/'language_after_inference')
    hashes=lambda p:{f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()}
    assert hashes(work/'memory_after_inference')==hashes(ROOT/'examples/run/memory')
    assert hashes(work/'language_after_inference')==hashes(ROOT/'model')
    old=read(ROOT/'verification/PREVIOUS_BASELINE.json');prior=ROOT.parent/old['release']
    assert hashes(prior)==old['files'] and sha(prior.with_name(prior.name+'.zip'))==old['zip_sha256']
    assert all(sha(ROOT/k)==v for k,v in old['copied_source'].items())
    write(ROOT/'verification/PRESERVATION.json',{'passed':True,'previous_files_unchanged':len(old['files']),
          'previous_zip_sha256':old['zip_sha256'],'copied_source_files':len(old['copied_source']),
          'language_model_unchanged':True,'retention_weights_unchanged_during_inference':True})
    write(ROOT/'verification/BENCHMARK.json',{'generate_requery_seconds':times[1:],'median_seconds':statistics.median(times[1:]),
          'memory_cost':memory.cost(),'partial_document_bases_bytes':model.codec.storage()['total_document_basis_bytes'],
          'generator_document_bases_bytes':model.document.codec.storage()['document_basis_bytes'],
          'fresh_packet_bytes':(ROOT/'examples/run/fresh-packet.json').stat().st_size,
          'scope':'7 warm serial repetitions after1 warmup, three-event demo. No total RSS, power, FLOPs, host-load isolation, or external teacher latency.'})
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()})
    development={scene_key(c['meaning']) for c in dataset('development',True)}
    a,b=dataset(100),dataset(101);assert not (development&{scene_key(c['meaning']) for c in a+b})
    assert not ({scene_key(c['meaning']) for c in a}&{scene_key(c['meaning']) for c in b})
    write(ROOT/'verification/DATA_AUDIT.json',{'passed':True,'datasets':2,'focal_episodes':48,'background_episodes':512,
          'development_eval_and_two_dataset_scenes_disjoint':True,'episode_ids_unique':len({c['episode'] for c in a+b})==560})
    p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
    write(ROOT/'verification/FINAL_TESTS.json',{'passed':True,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    cmd=[sys.executable,'-B','-m','ss_retention','generate','--model','model','--memory','examples/run/memory','--episode',example['episode'],'--packet','examples/run/fresh-packet.json','--order','reverse']
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
    assert __import__('json').loads(p.stdout)['text']==example['after_restart']['text']
    write(ROOT/'verification/CLI.json',{'command':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
    print({'passed':True,'example':example['after_restart']['text'],'old_files':len(old['files'])},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);p.add_argument('--verified',required=True);a=p.parse_args();main(a.work,a.verified)
