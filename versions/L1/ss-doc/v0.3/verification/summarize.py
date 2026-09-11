import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify

def main():
    verify();index=read(ROOT/'results/INDEX.json');groups={}
    for cid in index['conditions']:
        r=read(ROOT/'results/conditions'/(cid+'.json'));key=(r['background_load'],r['method'])
        a=groups.setdefault(key,{k:0 for k in ('conditions','queries','completed_correct','completed_wrong','needs_information','abstain',
                      'non_target_changed','generated_correct','generated_wrong','generated_abstain','reread_correct','requested_outputs',
                      'immediate_supported_correct','immediate_supported_wrong','immediate_held','retention_lost_after_correct_support',
                      'other_episode_queries','other_episode_completed','other_episode_raw_support','changed_anchor_queries','changed_anchor_completed','changed_anchor_raw_support',
                      'explicit_new_queries','explicit_new_preserved','explicit_new_held','explicit_new_overwritten','conflict_queries','conflict_held',
                      'drift_queries','drift_completed_old','drift_completed_new','drift_held','revised_queries','revised_completed_correct','revised_completed_wrong','revised_held')})
        a['conditions']+=1
        data={c['id']:c for c in read(ROOT/f'results/DATA-{r["data_seed"]}.json')}
        for row,immediate in zip(r['primary'],r['immediate'],strict=True):
            a['queries']+=1;a['requested_outputs']+=2
            c=data[row['case_id']];imok=immediate['value']==c['truth']
            a['immediate_supported_correct']+=imok;a['immediate_supported_wrong']+=immediate['value'] is not None and not imok;a['immediate_held']+=immediate['value'] is None
            status=row['completion']['status']
            if status=='completed':
                a['completed_correct' if row['final_equal'] else 'completed_wrong']+=1
                a['non_target_changed']+=not row['non_target_equal']
            else:a['needs_information' if status=='needs_information' else 'abstain']+=1
            a['retention_lost_after_correct_support']+=imok and not row['final_equal']
            for o in row['outputs']:
                if o['generation']['status']=='generated':a['generated_correct' if o['score']['semantic_equal'] else 'generated_wrong']+=1
                else:a['generated_abstain']+=1
                a['reread_correct']+=o['reread_equal']
        for name in ('other_episode','changed_anchor'):
            for row in r['controls'][name]:
                a[name+'_queries']+=1;a[name+'_completed']+=row['completion']['status']=='completed'
                a[name+'_raw_support']+=any(any(v['accepted_raw'] for v in q['recall']['raw'].values()) for q in row['completion'].get('audit',[]))
        for row in r['controls']['explicit_new']:
            a['explicit_new_queries']+=1
            if row['completion']['status']=='completed':a['explicit_new_preserved' if row['final_equal'] else 'explicit_new_overwritten']+=1
            else:a['explicit_new_held']+=1
        for row in r['controls']['conflict']:
            a['conflict_queries']+=1;a['conflict_held']+=row['completion']['status']=='needs_information'
        for d in r['unobserved_world_change']:
            a['drift_queries']+=1;a['drift_completed_old']+=d['completed'] and d['matches_old_reference'];a['drift_completed_new']+=d['completed'] and d['matches_new_reference'];a['drift_held']+=not d['completed']
        for row in r['revisions']:
            a['revised_queries']+=1
            if row['completion']['status']=='completed':a['revised_completed_correct' if row['final_equal'] else 'revised_completed_wrong']+=1
            else:a['revised_held']+=1
    rows=[{'background_episodes':key[0],'method':key[1],**v} for key,v in sorted(groups.items())]
    regression=read(ROOT/'results/REGRESSION.json')
    result={'rows':rows,'conditions':len(index['conditions']),'reference_arrays':index['reference_arrays'],
            'regression_cases':len(regression),'regression_correct':sum(r.get('score',{}).get('semantic_equal',False) for r in regression),
            'note':'Each row: 2 datasets x2 code seeds x24 episodes =96 queries; repeated load/method comparisons are paired, not independent language data.',
            'eligible_for_inference':False}
    write(ROOT/'verification/SUMMARY.json',result);print(__import__('json').dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
