from collections import defaultdict,Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify

verify();groups=defaultdict(list);held=[]
for cid in read(ROOT/'results/INDEX.json')['conditions']:
    r=read(ROOT/'results/conditions'/(cid+'.json'));data={c['id']:c for c in read(ROOT/f'results/DATA-{r["data_seed"]}.json')}
    g={'condition':cid,'protected_unchanged':r['protected_unchanged_during_background'],'cost':r['cost'],
       'cross_slot_swaps':0,'checkpoint_steps':{},'raw_unregistered_by_part':{}}
    for q in r['primary']:
        if q['wrong']:
            c=data[q['case_id']];a,b=c['scope']['mutable'];actual=q['final_observation']['cells'];expected=c['final']['cells']
            g['cross_slot_swaps']+=int(expected[a]!=expected[b] and actual[a]==expected[b] and actual[b]==expected[a])
        if q['status']!='completed' and r['method'].startswith('versioned_'):
            held.append({'condition':cid,'case_id':q['case_id'],'reason':q['completion'].get('reason'),'audit':q['completion'].get('audit')})
    for step in range(1,6):
        qs=[q for q in r['checkpoints'] if q['stage']==step];g['checkpoint_steps'][str(step)]={'queries':len(qs),'correct':sum(q['correct'] for q in qs),'wrong':sum(q['wrong'] for q in qs)}
    for mode in ('other_episode','changed_fixed'):
        for q in r['controls'][mode]:
            for a in q['raw_unregistered_support']:
                for part,raw in a['raw'].items():
                    key=mode+'/'+part;g['raw_unregistered_by_part'][key]=g['raw_unregistered_by_part'].get(key,0)+int(raw['accepted_raw'])
    groups[(r['background_episodes'],r['method'])].append(g)
rows=[]
for (load,method),conditions in sorted(groups.items()):
    raw=Counter()
    for c in conditions:raw.update(c['raw_unregistered_by_part'])
    rows.append({'background_episodes':load,'method':method,'conditions':conditions,'raw_unregistered_by_part':dict(raw),
                 'cross_slot_swaps':sum(c['cross_slot_swaps'] for c in conditions)})
write(ROOT/'verification/AUDIT.json',{'passed':True,'rows':rows,'versioned_held_cases':held,
      'note':'Post-primary read-only audit;raw unknown-scope scores use evaluator-assumed revision numbers,not inference access to unknown history.'})
print({'passed':True,'rows':len(rows),'versioned_held_cases':len(held)},flush=True)
