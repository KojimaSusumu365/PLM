"""Standalone, posthoc cost diagnostic; no model selection or result tuning."""
import itertools,json,platform,statistics,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from plm_l1_v011.training import fit

def main():
    tasks=json.loads((ROOT/'data/evaluation.json').read_text(encoding='utf-8'))
    tasks=[t for t in tasks if t['family'] in ('unary','xor2','parity3') and t['id'].endswith('/0')]
    rows=[]
    for task in tasks:
        for rep,selector,backend in itertools.product(('additive','product','hybrid3'),('off','validation'),('ss','exact')):
            fits=[];queries=[]
            for trial in range(3):
                start=time.perf_counter();m,_,_=fit(task['train'],task['selection'],representation=rep,selector=selector,backend=backend,dimension=2048,seed='evaluation-0');fits.append(time.perf_counter()-start)
                for row in task['test']:m.predict(row['context'])
                start=time.perf_counter()
                for _ in range(2):
                    for row in task['test']:m.predict(row['context'])
                queries.append((time.perf_counter()-start)/32)
            rows.append({'task_id':task['id'],'method':'/'.join((rep,selector,backend)),'fit_seconds':fits,'warm_query_seconds':queries,
                         'median_fit_seconds':statistics.median(fits),'median_warm_query_seconds':statistics.median(queries),'storage':m.storage()})
        print('cost',task['id'],flush=True)
    r={'scope':'Standalone single process after full evaluations. Three prelisted standard tasks, D2048, first seed, 3 repeats. Warm complete-context query includes encoding and packet validation, excludes calibration. Not a full-language or total-energy benchmark.',
       'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'rows':rows}
    with (ROOT/'verification/BENCHMARK.json').open('x',encoding='utf-8') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    for method in sorted({x['method'] for x in rows}):
        subset=[x for x in rows if x['method']==method]
        print(method,'fit_s',statistics.median(x['median_fit_seconds'] for x in subset),'query_ms',1000*statistics.median(x['median_warm_query_seconds'] for x in subset),flush=True)

if __name__=='__main__':main()
