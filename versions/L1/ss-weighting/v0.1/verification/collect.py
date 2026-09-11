"""Post-evaluation aggregation, byte-repeatability and preservation audit."""
from collections import Counter
import json
import statistics
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.weight_integrity import write,sha,verify
from evaluation.weight_cases import memory_case
from ss_weighting.training import fit


def main():
    repeat=Path(sys.argv[1]).resolve()
    verification=ROOT/'verification'
    matches=[]
    for p in sorted((ROOT/'results').rglob('*')):
        if p.is_file() and p.name!='PERFORMANCE.json':
            rel=p.relative_to(ROOT/'results')
            h=sha(p);other=sha(repeat/rel)
            assert h==other
            matches.append({'path':rel.as_posix(),'sha256':h,'repeat_sha256':other})
    write(verification/'REPEATABILITY.json',{'freeze_hash':verify(),'files':matches,'all_equal':True,'excluded':['PERFORMANCE.json']})
    baseline=json.loads((verification/'BASELINE.json').read_text(encoding='utf-8'))
    changed=[n for n,h in baseline['previous_files'].items() if sha(ROOT.parent/n)!=h]
    assert not changed
    write(verification/'PRESERVATION.json',{'previous_files':len(baseline['previous_files']),'all_unchanged':True,'changed':changed})
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    sums={};structured={}
    for row in result['memory']:
        for c in row['conditions']:
            k=(row['known_count'],row['dimension'],row['method'],c['condition'])
            sums.setdefault(k,Counter()).update(c['metrics'])
    memory=[]
    for (n,d,m,c),v in sums.items():
        memory.append(dict(known_count=n,dimension=d,method=m,condition=c,**v))
    for row in result['structured']:
        family=row['family']
        group=family if family.startswith('paired_') or family=='outside_order4' else 'structured' if family in ('roles','polarity_modality') else 'standard'
        for stage in row['stages']:
            k=(group,row['method'],row['dimension'],row['budget'],stage['kind'])
            structured.setdefault(k,Counter()).update({n:v for n,v in stage['metrics'].items() if type(v) is int})
    sr=[dict(group=g,method=m,dimension=d,budget=b,kind=k,**v) for (g,m,d,b,k),v in structured.items()]
    paired=[]
    for row in memory:
        if row['method'] not in ('positive','residual'):continue
        base=next(x for x in memory if x['method']=='uniform' and all(x[k]==row[k] for k in ('known_count','dimension','condition')))
        paired.append({k:row[k] for k in ('known_count','dimension','method','condition')}|
                      {k:row[k]-base[k] for k in ('known_correct','known_wrong','known_abstain','unknown_false_accept')})
    structural_comparison=[]
    for row in result['structured']:
        if row['method'] not in ('positive','residual'):continue
        base=next(x for x in result['structured'] if x['method']=='uniform' and all(x[k]==row[k] for k in ('task_id','dimension','seed','budget')))
        structural_comparison.append({'task_id':row['task_id'],'method':row['method'],'dimension':row['dimension'],'seed':row['seed'],'budget':row['budget'],
                                     'masks_equal':base['candidate_masks']==row['candidate_masks'],
                                     'predictions_equal':all(a['predictions']==b['predictions'] for a,b in zip(base['stages'],row['stages']))})
    write(verification/'SUMMARY.json',{'memory':memory,'structured':sr,'matched_deltas':paired,'structured_comparison':structural_comparison,
                                      'memory_models':len(result['memory']),'exact_models':len(result['exact']),'structured_models':len(result['structured'])})
    timing=[]
    for d,n in ((128,64),(128,256),(512,64),(512,256)):
        teachers=memory_case('weight-benchmark',n)['teachers']
        for method in ('uniform','positive','residual','exact'):
            times=[]
            for trial in range(3):
                start=time.perf_counter()
                model,audit=fit(teachers,dimension=d,method='uniform' if method=='exact' else method,backend='exact' if method=='exact' else 'ss')
                times.append(time.perf_counter()-start)
            timing.append({'dimension':d,'known_count':n,'method':method,'seconds':times,'median_ms':statistics.median(times)*1000,
                           'storage':model.storage(),'audit':audit})
    write(verification/'BENCHMARK.json',{'scope':'Single process after full evaluations. Four prelisted shapes, three repeats. Fit includes validation/encoding/learning and its diagnostics; no evaluation queries. Not online update time, energy, peak RSS, or matched total training memory.', 'rows':timing})
    for r in memory:
        if r['known_count']==256 and r['condition']=='clean': print(r,flush=True)
    print(json.dumps({'equal_files':len(matches),'preserved_files':len(baseline['previous_files']),
                      'structured_comparisons':len(structural_comparison),'structured_all_equal':all(x['predictions_equal'] for x in structural_comparison)}),flush=True)


if __name__=='__main__':main()
