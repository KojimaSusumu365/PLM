"""Descriptive aggregation of frozen results; does not fit or tune the learner."""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',required=True); a=p.parse_args()
    r=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    aggregated={}; failures=[]
    for row in r['synthetic']:
        group=('standard' if row['train_count']==24 and row['flipped_labels']==0 else 'stress',row['method'],row['dimension'],row['selection_enabled'])
        if group not in aggregated: aggregated[group]=Counter()
        c=aggregated[group]; c['runs']+=1; c['fallback_full_context']+=row['fallback_full_context']
        for stage in ('symbolic_projection','phase_retrieval'):
            for k,v in row[stage].items(): c[stage+'/'+k]+=v
        c['unregistered_accepted']+=row['unregistered_accepted']; c['unregistered_requests']+=row['unregistered_requests']
        if row['method']=='ss' and row['selection_enabled'] and (row['fallback_full_context'] or row['phase_retrieval']['wrong']):
            failures.append({k:row[k] for k in ('task_id','dimension','seed','selected_masks','true_dependencies','fallback_full_context','symbolic_projection','phase_retrieval')})
    output={'source_result_digest':r['result_digest'],'aggregates':[{'condition':key[0],'method':key[1],'dimension':key[2],'selection_enabled':key[3],**dict(v)} for key,v in aggregated.items()],
            'selected_failure_conditions':failures,
            'counting_note':'450 fitted conditions are repeated combinations of 10 task variants, training sizes, flips, seeds, dimensions and methods, not 450 independent linguistic tasks. Standard D rows contain 80 task-specific heldout examples repeated over two code seeds. All-2 OOD probes are only one artificial key per condition.'}
    with Path(a.out).open('x',encoding='utf-8') as f: f.write(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(failures[:5]))

if __name__=='__main__': main()
