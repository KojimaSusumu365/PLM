from collections import defaultdict,Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write

groups=defaultdict(list)
for cid in read(ROOT/'results/INDEX.json')['conditions']:
    r=read(ROOT/'results/conditions'/(cid+'.json'));groups[(r['background_episodes'],r['method'])].append(r)
rows=[];failures=[]
for (load,method),conditions in sorted(groups.items()):
    qs=[q for c in conditions for q in c['primary']];outs=[o for q in qs for o in q['outputs']]
    row={'background_episodes':load,'method':method,'queries':len(qs),'correct':sum(q['correct'] for q in qs),
         'wrong':sum(q['wrong'] for q in qs),'held':sum(q['status']!='completed' for q in qs),
         'old_value_reappearance':sum(q['old_value_reappearance'] for q in qs),
         'non_target_changed':sum(q['non_target_changed'] for q in qs),'requested_outputs':len(qs)*2,
         'generated_correct':sum(bool(o['score'] and o['score']['semantic_equal']) for o in outs),
         'generated_wrong':sum(bool(o['score'] and not o['score']['semantic_equal']) for o in outs),
         'reread_correct':sum(o['reread_equal'] for o in outs),'hold_reasons':dict(Counter(q['completion'].get('reason') for q in qs if q['status']!='completed')),
         'rejected_confirmations':sum(len(c['rejected_confirmations']) for c in conditions),'controls':{},
         'checkpoint_correct':sum(q['correct'] for c in conditions for q in c['checkpoints']),
         'checkpoint_queries':sum(len(c['checkpoints']) for c in conditions),
         'coefficient_bytes':conditions[0]['cost']['total_coefficient_bytes']}
    for mode in conditions[0]['controls']:
        controls=[q for c in conditions for q in c['controls'][mode]]
        row['controls'][mode]={'queries':len(controls),'correct':sum(q['correct'] for q in controls),
            'wrong':sum(q['wrong'] for q in controls),'held':sum(q['status']!='completed' for q in controls),
            'old_value_reappearance':sum(q['old_value_reappearance'] for q in controls),
            'current_known_changed':sum(q['non_target_changed'] for q in controls),
            'raw_unregistered_target_support':sum(any(p['accepted_raw'] for p in a['raw'].values()) for q in controls for a in q.get('raw_unregistered_support',[]))}
    rows.append(row)
    for c in conditions:
        for q in c['primary']:
            if q['wrong']:failures.append({'condition':c['condition'],'query':q})
record={'rows':rows,'conditions':sum(len(v) for v in groups.values()),'regression_count':len(read(ROOT/'results/REGRESSION.json')),
        'note':'Each row96 paired queries from48 focal scenes x2 code seeds. Across conditions1152 queries,not independent language samples.',
        'eligible_for_inference':False}
write(ROOT/'verification/SUMMARY.json',record);write(ROOT/'verification/PRIMARY_FAILURES.json',failures)
for r in rows:print({k:r[k] for k in ('background_episodes','method','correct','wrong','held','generated_correct')},flush=True)
