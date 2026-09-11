import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify
from evaluation.experiment import query
from ss_partial.runtime import PartialModel
from ss_retention.memory import CorrectionMemory

verify();index=read(ROOT/'results/INDEX.json');model=PartialModel.load(ROOT/'model');rows=[];wrong=[];held=[];collateral=[]
for cid in index['conditions']:
    r=read(ROOT/'results/conditions'/(cid+'.json'));data={c['id']:c for c in read(ROOT/f'results/DATA-{r["data_seed"]}.json')}
    raw={}
    for mode in ('other_episode','changed_anchor'):
        for q in r['controls'][mode]:
            for a in q['completion'].get('audit',[]):
                for part,v in a['recall']['raw'].items():raw[mode+'/'+part]=raw.get(mode+'/'+part,0)+v['accepted_raw']
    protected_support=0
    for q in r['primary']:
        case=data[q['case_id']]
        for a in q['completion'].get('audit',[]):
            protected_support+=a['recall']['raw'].get('protected',{}).get('value')==case['truth']
        if q['completion']['status']=='completed' and not q['final_equal']:
            wrong.append({'condition':cid,'case':case,'query':q})
        if r['method'].startswith('split') and q['completion']['status']!='completed':held.append({'condition':cid,'case_id':q['case_id'],'completion':q['completion']})
    rows.append({'condition':cid,'protected_supported_correct':protected_support,'raw_unregistered_by_part':raw,
                 'protected_coefficients_unchanged':r['protected_coefficients_unchanged']})
    revised=CorrectionMemory.load(ROOT/'results/revised_memories'/cid,model.codec.candidates)
    focal=[c for c in data.values() if c['kind']=='focal'];checks=[]
    for i,c in enumerate(focal[6:],6):
        after=query(model,revised,c,('ambiguous','unobserved','unreadable')[i%3],outputs=False)
        checks.append({'case_id':c['id'],'before_correct':r['primary'][i]['final_equal'],'after_correct':after['final_equal'],
                       'after_status':after['completion']['status'],'after_wrong':after['completion']['status']=='completed' and not after['final_equal']})
    collateral.append({'condition':cid,'queries':checks})
write(ROOT/'verification/AUDIT.json',{'passed':True,'rows':rows,'primary_wrong_completion_cases':wrong,'protected_held_cases':held,
      'note':'Read-only audit, no parameter changes; protected raw support distinguished from final completed documents.'})
write(ROOT/'verification/REVISION_COLLATERAL.json',{'post_primary_supplement':True,'rows':collateral,
      'note':'Remaining18 episodes after6 revisions: semantic completion only, not additional full-text generation. Not added to primary results.'})
print({'passed':True,'primary_wrong_cases':len(wrong),'protected_held':len(held),'supplement_requeries':sum(len(r['queries']) for r in collateral)},flush=True)
