"""Artifacts and reproducibility, not used by the frozen evaluator or runtime."""
import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
from evaluation.oracle import parse,localize,scored
from evaluation.experiment import semantic,signal_hash
from plm_l1_v09.component.algebra import digest
from ss_document.runtime import DocumentModel

EXAMPLES=(
    '太郎が花子を助けた。その後、花子が健太を褒めた。',
    '太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が由紀を訪ねた。',
    'もし花子を太郎が助けなかったら。その前に、健太を由紀が褒めた。その後、次郎が美咲を訪ねた。',
)


def main(repeat,oldroot):
    verify();repeat=Path(repeat);oldroot=Path(oldroot)
    files={p.relative_to(ROOT/'results').as_posix():sha(p) for p in (ROOT/'results').rglob('*') if p.is_file() and p.name!='PERFORMANCE.json'}
    actual={p.relative_to(repeat).as_posix():sha(p) for p in repeat.rglob('*') if p.is_file() and p.name!='PERFORMANCE.json'}
    assert files==actual
    write(ROOT/'verification/REPEATABILITY.json',{'passed':True,'files':files,'byte_equal_files':len(files),
          'excluded':['PERFORMANCE.json'],'digest':digest(files)})
    baseline=read(ROOT/'verification/PREVIOUS_BASELINE.json');preserved=[]
    for name,b in baseline.items():
        old=oldroot/name;now={p.relative_to(old).as_posix():sha(p) for p in old.rglob('*') if p.is_file()}
        assert b['files']==now and b['zip_sha256']==sha(oldroot/(name+'.zip'))
        preserved.append({'release':name,'unchanged_files':len(now),'zip_sha256':b['zip_sha256']})
    write(ROOT/'verification/PRESERVATION.json',{'passed':True,'releases':preserved,
          'copied_v09_python_files':len(list((ROOT/'plm_l1_v09').rglob('*.py')))})
    proc=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    write(ROOT/'verification/TESTS.json',{'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),'other_os_tested':False})
    model=DocumentModel.load(ROOT/'results/models/s0-c0');outputs=[]
    for i,text in enumerate(EXAMPLES):
        result=model.read(text);assert result['status']=='read';packet=result['packet'];m=model.recover(packet)['meaning']
        out=model.generate(packet,'reverse');expected=localize(m,list(reversed(m['presentation'])),['subject']*len(m['events']))
        assert scored(expected,out['text'])['semantic_equal']
        write(ROOT/f'examples/packet-{i+1}.json',packet)
        outputs.append({'input':text,'output':out['text'],'meaning':m,'packet':f'packet-{i+1}.json','packet_sha256':signal_hash(packet),
                        'order':'reverse','is_independent_evaluation_sample':False})
    write(ROOT/'examples/EXAMPLES.json',outputs)
    # Separate processes for the documented commands; outputs outside the sealed release.
    cli=repeat.parent/'ssdoc-cli';cli.mkdir(exist_ok=False);commands=[]
    for args in [
        ['-m','ss_document','read','--model','results/models/s0-c0','--text',EXAMPLES[1],'--out',str(cli/'packet.json')],
        ['-m','ss_document','generate','--model','results/models/s0-c0','--packet',str(cli/'packet.json'),'--order','reverse'],
        ['-m','ss_document','recover','--model','results/models/s0-c0','--packet',str(cli/'packet.json')],
        ['examples/demo.py']]:
        p=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');assert p.returncode==0,p.stderr
        commands.append({'arguments':args,'returncode':p.returncode,'stdout':p.stdout})
    assert json.loads(commands[1]['stdout'])['text']==outputs[1]['output']
    assert json.loads(commands[3]['stdout'])['output']==outputs[1]['output']
    write(ROOT/'verification/CLI.json',{'passed':True,'commands':commands})
    # Benchmark is per representative two/three-event input, fixed warm memories,7 serial repeats.
    benches=[]
    for text in EXAMPLES[:2]:
        packet=model.read(text)['packet'];model.generate(packet,'reverse');rs=[];gs=[]
        for _ in range(7):
            start=time.perf_counter();model.read(text);rs.append(time.perf_counter()-start)
            start=time.perf_counter();model.generate(packet,'reverse');gs.append(time.perf_counter()-start)
        benches.append({'events':text.count('。'),'read_seconds':rs,'generate_seconds':gs,
                        'median_read_seconds':float(np.median(rs)),'median_generate_seconds':float(np.median(gs)),
                        'packet_json_bytes':len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode('utf-8')),
                        **model.codec.storage()})
    write(ROOT/'verification/BENCHMARK.json',{'rows':benches,'scope':'7 serial repetitions, warm caches. Other host/process load not isolated; not full RSS/FLOPs or general speed claims.'})
    print(json.dumps({'repeat_equal_files':len(files),'preservation':preserved,'examples':outputs},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repeat',required=True);p.add_argument('--oldroot',required=True);a=p.parse_args();main(a.repeat,a.oldroot)
