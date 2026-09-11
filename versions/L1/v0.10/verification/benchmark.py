"""Posthoc standalone scalar diagnostic; does not tune or replace frozen results."""
import json,platform,statistics,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.support import data
from evaluation.synthetic import pairs
from plm_l1_v010.memory import fit_memory

def main():
    tasks=[t for t in data('dependencies_evaluation') if t['train_count']==24 and t['flipped_labels']==0 and t['id'].split('/')[2]=='0']
    assert len(tasks)==5
    methods=('ss_multi','symbolic_multi','ss_single','v09_single','v09_pooled')
    records=[]
    # Warm import/allocation paths with development data, not a reported timing.
    warm=data('ambiguity_development')[0]
    for method in methods:
        fit_memory(pairs(warm['train']),pairs(warm['selection_validation']),method=method,dimension=2048)
    for task in tasks:
        for method in methods:
            fit_times=[];query_times=[]
            for repeat in range(3):
                start=time.perf_counter()
                model=fit_memory(pairs(task['train']),pairs(task['selection_validation']),method=method,dimension=2048,seed='candidate-evaluation-0')
                fit_times.append(time.perf_counter()-start)
                for row in task['evaluation']:model.predict(row['context'])
                start=time.perf_counter()
                for _ in range(10):
                    for row in task['evaluation']:model.predict(row['context'])
                query_times.append(time.perf_counter()-start)
            records.append({'task_id':task['id'],'method':method,'dimension':2048,'fit_seconds':fit_times,
                            'fit_median_seconds':statistics.median(fit_times),'query_160_seconds':query_times,
                            'query_median_microseconds':statistics.median(query_times)/160*1e6,
                            'candidates':len(model.memories),'storage':model.storage()})
        print('benchmark',task['id'],flush=True)
    summary={method:{'median_of_five_fit_medians_seconds':statistics.median(r['fit_median_seconds'] for r in records if r['method']==method),
                     'median_of_five_query_medians_microseconds':statistics.median(r['query_median_microseconds'] for r in records if r['method']==method)} for method in methods}
    result={'scope':'Standalone single-process posthoc diagnostic after full evaluations and strict refit ended. Five standard scalar tasks, one field permutation, D2048, seed0, three repetitions. No risk calibration in timing. Not full-language latency, general benchmark, or OS-isolated measurement.',
            'environment':{'python':sys.version,'numpy':np.__version__,'platform':platform.platform()},'records':records,'summary':summary}
    with (ROOT/'verification/BENCHMARK.json').open('x',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
