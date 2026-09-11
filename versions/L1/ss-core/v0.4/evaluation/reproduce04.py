"""Offline regeneration and cold numeric-only runtime checks."""
import argparse,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from ss_core_v04.compile import compile_bundle
from .integrity import read,write,sha
from .verify04 import verify
ROOT=Path(__file__).resolve().parents[1]

def rebuild():
    with tempfile.TemporaryDirectory(prefix='plm-working04-build-') as d:
        out=Path(d)/'bundle';compile_bundle(ROOT,out)
        checks={p.name:sha(p)==sha(ROOT/'bundle04'/p.name) for p in out.iterdir()}
        assert all(checks.values()),checks
    return checks

def cold(source):
    with tempfile.TemporaryDirectory(prefix='plm-working04-cold-') as d:
        dest=Path(d)
        files=['ss_core_v04/__init__.py','ss_core_v04/runtime.py','ss_core_v04/memory.py','ss_core_v04/signal.py',
               'ss_core_v03/waveform.py','plm_l1_v09/thresholds.py','plm_l1_v09/component/algebra.py',
               'plm_l1_v09/component/banked.py','plm_l1_v09/component/projection.py','bundle04/bundle.json','bundle04/signals.npz']
        for name in files:
            p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
        for name in ('plm_l1_v09/__init__.py','plm_l1_v09/component/__init__.py','ss_core_v03/__init__.py'):
            shutil.copy2(ROOT/'cold/neutral_init.py',dest/name)
        shutil.copy2(ROOT/'cold/entry.py',dest/'entry.py')
        shutil.copytree(source/'wm',dest/'wm');shutil.copy2(source/'controls.npz',dest/'controls.npz')
        assert not any((dest/n).exists() for n in ('model','data','programs','evaluation','bundle04/IO.json','ss_core_v04/boundary.py','ss_core_v04/compile.py'))
        process=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(dest/'entry.py')],cwd=dest,env={**os.environ,'PYTHONIOENCODING':'utf-8'},capture_output=True,text=True,encoding='utf-8',check=True)
        result=json.loads(process.stdout);assert result['result']['text']==read(source/'EXPECTED.json')['text'] and result['result']['status']=='generated'
        return {'passed':True,'inventory':sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()),**result}

def compare(a,b):
    def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.name.startswith('TIMING-')}
    x,y=inventory(a),inventory(b);assert x==y,sorted(k for k in set(x)|set(y) if x.get(k)!=y.get(k))
    return {'identical_files_excluding_timing':len(x)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--run1',default='results/run1');p.add_argument('--run2',default='results/run2');a=p.parse_args()
    verify();r={'rebuild':rebuild(),'cold':cold(ROOT/a.run1/'cold'),'repeat':compare(ROOT/a.run1,ROOT/a.run2)}
    write(a.output,r);print(json.dumps(r,ensure_ascii=False))
