"""Post-evaluation timing diagnostic, no tuning or changes to frozen accuracy data.

Run after the parallel deterministic and legacy runs finish. This is a local
microbenchmark, not an end-to-end production RAM/latency equivalence experiment.
"""
import argparse,json,random,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.support import data
from evaluation.synthetic import run

def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); a=p.parse_args()
    tasks=[t for t in data('dependencies_evaluation') if t['train_count']==24 and not t['flipped_labels']]
    records=[]
    for repeat in range(3):
        schedule=[(t,m,s) for t in tasks for m in ('ss','symbolic','id3','full') for s in ('selection-evaluation-0','selection-evaluation-1')]
        random.Random(901+repeat).shuffle(schedule)
        for task,method,seed in schedule:
            _,perf=run(task,method,2048,seed); records.append(dict(perf,repeat=repeat))
    summary={}
    for method in ('ss','symbolic','id3','full'):
        rows=[r for r in records if r['method']==method]
        summary[method]={'runs':len(rows),**{k:statistics.median(r[k] for r in rows) for k in ('selection_seconds','compile_seconds','phase_query_seconds','owned_heap_bytes')}}
    with Path(a.out).open('x',encoding='utf-8') as f:
        f.write(json.dumps({'summary':summary,'records':records,'scope':'D2048, standard tasks, random method order, 3 repeats, OPENBLAS_NUM_THREADS=1; no other task evaluations deliberately running. OS scheduling and full process RAM uncontrolled.'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__': main()
