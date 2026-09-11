"""Posthoc summaries and repeatability; no fit, thresholds or source tuning."""
import argparse,collections,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import sha,verify_freeze

def write(name,value):
    with (ROOT/'verification'/name).open('x',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def totals(rows):
    fields=('requests','correct','wrong','abstained','accepted','ambiguous_requests','unsafe_confirmations','identifiable_requests','identifiable_correct','identifiable_abstained','ambiguous_correctly_abstained','compatible_but_unjustified','unsupported_requests')
    r={k:sum(x[k] for x in rows) for k in fields};r['coverage']=r['accepted']/r['requests'] if r['requests'] else None;r['selective_risk']=r['wrong']/r['accepted'] if r['accepted'] else None;return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--repeat',required=True);p.add_argument('--prior');a=p.parse_args();repeat=Path(a.repeat)
    r=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'));perf=json.loads((ROOT/'results/PERFORMANCE.json').read_text(encoding='utf-8'))
    groups={};families={};cost={}
    for i,run in enumerate(r['runs']):
        category='ambiguity' if run['family']=='ambiguity' else 'small' if run['task_id'].endswith('/small') else 'structured' if run['family'] in ('roles','polarity_modality') else 'standard'
        if not run['enabled']:category='zero_weights'
        prefix=(category,run['after'],run['method'],run['dimension'],run['budget'])
        cost.setdefault(prefix,[]).append((run,perf['runs'][i]))
        for s in run['stages']:
            groups.setdefault(prefix+(s['kind'],s['fraction']),[]).append(s)
            families.setdefault((run['family'],)+prefix+(s['kind'],s['fraction']),[]).append(s)
    def entries(groups,fields):
        return [dict(zip(fields,k),runs=len(v),raw=totals([x['raw'] for x in v]),gated=totals([x['gated'] for x in v])) for k,v in groups.items()]
    rows=entries(groups,('category','after','method','dimension','budget','kind','fraction'))
    by_family=entries(families,('family','category','after','method','dimension','budget','kind','fraction'))
    costs=[]
    for key,values in cost.items():
        arrays=[r['storage']['complex_weight_bytes'] for r,p in values]
        costs.append(dict(zip(('category','after','method','dimension','budget'),key),models=len(values),
                     weight_bytes_range=[min(arrays),max(arrays)],metadata_bytes_range=[min(r['storage']['metadata_utf8_bytes'] for r,p in values),max(r['storage']['metadata_utf8_bytes'] for r,p in values)],
                     exact_count_entries_range=[min(r['storage']['integer_count_entries'] for r,p in values),max(r['storage']['integer_count_entries'] for r,p in values)],
                     warm_codebook_bytes_range=[min(r['storage']['warm_codebook_array_bytes'] for r,p in values),max(r['storage']['warm_codebook_array_bytes'] for r,p in values)],
                     candidate_counts=dict(collections.Counter(r['storage']['members'] for r,p in values)),
                     median_fit_seconds=statistics.median(p['fit_seconds'] for r,p in values),
                     median_evaluation_seconds=statistics.median(p['evaluation_seconds'] for r,p in values),
                     max_training_cache_bytes=max(p['training_term_cache_bytes'] for r,p in values)))
    matched=[]
    for selector in ('off','validation'):
        for kind in ('complete','semantic_missing'):
            selected=[x for x in r['matched_coverage'] if x['group'][2:]==[kind,selector]]
            names=selected[0]['metrics'] if selected else []
            matched.append({'selector':selector,'kind':kind,'groups':len(selected),'zero_common_groups':sum(x['accepted_per_method']==0 for x in selected),
                            'accepted_per_method':sum(x['accepted_per_method'] for x in selected),
                            'wrong_by_method':{n:sum(x['metrics'][n]['wrong'] for x in selected) for n in names}})
    write('RESULT_SUMMARY.json',{'fitted_conditions':len(r['runs']),'checks_by_kind':dict(collections.Counter(c['kind'] for c in r['checks'])),
                              'aggregates':rows,'by_family':by_family,'costs':costs,'matched':matched,
                              'timing_scope':'Main-run timings overlap the independent repeat. Cost metadata is descriptive, not a matched total-RAM or isolated speed benchmark.'})
    files=[]
    for f in sorted((ROOT/'results').rglob('*')):
        if not f.is_file() or f.name=='PERFORMANCE.json':continue
        rel=f.relative_to(ROOT/'results');b=repeat/rel
        files.append({'file':rel.as_posix(),'sha256':sha(f),'repeat_sha256':sha(b),'equal':sha(f)==sha(b)})
    assert files and all(x['equal'] for x in files)
    write('REPEATABILITY.json',{'two_full_numeric_runs':True,'source_freeze':verify_freeze(),'files':files,'excluded':['PERFORMANCE.json']})
    if a.prior:
        previous_result=json.loads((Path(a.prior)/'EVALUATION.json').read_text(encoding='utf-8'))
        old={k:v for k,v in previous_result.items() if k not in ('freeze_hash','result_digest')}
        current={k:v for k,v in r.items() if k not in ('freeze_hash','result_digest')}
        assert old==current
        write('VERIFIER_PATCH_NUMERIC_AUDIT.json',{'all_numerical_results_identical_before_after_verifier_only_patch':True,
              'old_freeze':previous_result['freeze_hash'],'current_freeze':r['freeze_hash'],
              'excluded_from_comparison':['freeze_hash','result_digest'],'scope':'Verifies that correcting stderr log parsing did not change numerical results, masks, thresholds or saved-model fingerprints.'})
    previous=json.loads((ROOT/'verification/PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
    changed=[n for n,h in previous.items() if not (ROOT.parent/n).is_file() or sha(ROOT.parent/n)!=h]
    assert not changed,changed
    write('PRESERVATION_CHECK.json',{'previous_files':len(previous),'all_preserved':True,'changed':changed,'shared_history_excluded':'PLM-SS-LANGUAGE-DIRECTION.md append only',
                                     'v010_zip_sha256':sha(ROOT/'vendor/PLM-L1-v0.10.zip')})
    print(json.dumps({'models':len(r['runs']),'repeat_equal_files':len(files),'preserved_previous_files':len(previous)}),flush=True)

if __name__=='__main__':main()
