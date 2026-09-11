"""Parallel independent trials; unchanged numeric runtime and scoring.

Each shard starts a fresh receiver. No answer, memory, trace or cache is shared.
Run 1 and run 2 use identical shard boundaries and are compared byte-for-byte.
"""
import argparse,concurrent.futures,json,shutil,time
from pathlib import Path
from .experiment04 import run
from .integrity import read,write
from .verify04 import verify
ROOT=Path(__file__).resolve().parents[1]
SIZES={'main':40,'updates':12,'partial':4,'faults':10}
NAMES={'main':'MAIN.json','updates':'UPDATES.json','partial':'PARTIAL.json','faults':'FAULTS.json'}

def worker(job):
    repetition,suite,index,out=job
    run(Path(out)/repetition/'shards'/f'{suite}-{index}',suite,[index])
    return repetition,suite,index

def collect(out,repetition):
    root=out/repetition;summary={'freeze':verify(),'execution':'one independent trial per process job'}
    for suite,size in SIZES.items():
        rows=[];total={}
        for i in range(size):
            shard=root/'shards'/f'{suite}-{i}';rows.extend(read(shard/NAMES[suite]))
            s=read(shard/f'SUMMARY-{suite}.json')[suite]
            for key,value in s.items():
                if type(value) in (int,float):total[key]=total.get(key,0)+value
                else:
                    assert key not in total or total[key]==value;total[key]=value
            # Keep original shard files for audit, copy useful numeric state only.
            if (shard/'cold').exists():shutil.copytree(shard/'cold',root/'cold')
        write(root/NAMES[suite],rows);summary[suite]=total
    write(root/'SUMMARY-all.json',summary)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='results');p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    assert 1<=a.workers<=8
    freeze=verify();out=Path(a.output).resolve();started=time.perf_counter()
    assert not any((out/r).exists() for r in ('run1','run2')),'use fresh output directory'
    jobs=[(r,suite,i,str(out)) for suite,size in SIZES.items() for i in range(size) for r in ('run1','run2')]
    with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(worker,job) for job in jobs]
        for count,f in enumerate(concurrent.futures.as_completed(futures),1):
            print(json.dumps({'completed_jobs':count,'of':len(jobs),'job':f.result()}),flush=True)
    summaries={r:collect(out,r) for r in ('run1','run2')}
    write(out/'PARALLEL.json',{'workers':a.workers,'jobs':len(jobs),'freeze':freeze,'independent_receivers':True,'seconds':round(time.perf_counter()-started,3)})
    print(json.dumps(summaries,ensure_ascii=False),flush=True)
