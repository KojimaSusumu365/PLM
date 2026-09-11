"""Post-hoc diagnostic only: did the frozen selector revisit actual relapse cases?"""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ss_active.selection import diagnostics
from evaluation.cases import truth_map
from evaluation.metrics import probes,decisions
from evaluation.integrity import write,verify
verify();result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
cases={(c['seed'],c['size']):c for c in json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['evaluation']}
aggregate={};details=[]
with np.load(ROOT/'results/SCORES.npz',allow_pickle=False) as arrays:
    for run in result['runs']:
        key=(run['size'],run['world'],run['strategy'])
        a=aggregate.setdefault(key,{'first_corrected':0,'relapsed_after_D':0,'drop_eligible_at_post_D':0,'relapsed_reasked_later':0,
            'relapsed_correct_q32':0,'relapsed_correct_E':0,'revisit_presentations':0,'revisit_was_wrong':0,'revisit_immediately_fixed':0})
        case=cases[run['data_seed'],run['size']];truth=truth_map(case,run['world']);ids=[r['id'] for r in probes(case)];positions={k:i for i,k in enumerate(ids)}
        first={e['request']['selection']['selected_id']:i for i,e in enumerate(run['trace'][:16]) if e['before']['tentative'] is not None and e['before']['tentative']!=e['teacher_label'] and e['after']['tentative']==e['teacher_label']}
        d_scores=arrays[run['checkpoints'][2]['array']];d=decisions(d_scores);d_margins=diagnostics(d_scores)['margin']
        q32=decisions(arrays[run['checkpoints'][4]['array']]);end=decisions(arrays[run['checkpoints'][5]['array']]);after=arrays[run['trace_prefix']+'_after']
        later={e['request']['selection']['selected_id'] for e in run['trace'][16:]};a['first_corrected']+=len(first)
        for selected,index in first.items():
            ix=positions[selected];y=int(truth[selected])
            if d['tentative'][ix]==y:continue
            old_margin=float(diagnostics(after[index:index+1])['margin'][0]);margin=float(d_margins[ix]);drop=old_margin-margin
            eligible=drop>=run['config']['drop_margin'];reasked=selected in later
            a['relapsed_after_D']+=1;a['drop_eligible_at_post_D']+=int(eligible);a['relapsed_reasked_later']+=int(reasked)
            a['relapsed_correct_q32']+=int(q32['tentative'][ix]==y);a['relapsed_correct_E']+=int(end['tentative'][ix]==y)
            details.append({'size':run['size'],'world':run['world'],'strategy':run['strategy'],'data_seed':run['data_seed'],'code_seed':run['code_seed'],
                'acquisition_seed':run['acquisition_seed'],'id':selected,'post_teacher_margin':old_margin,'post_D_margin':margin,'margin_drop':drop,
                'drop_eligible_at_post_D':eligible,'reasked_later':reasked,'correct_at_E':bool(end['tentative'][ix]==y)})
        for e in run['trace']:
            if e['request']['selection']['route']!='revisit':continue
            a['revisit_presentations']+=1;wrong=e['before']['tentative'] is not None and e['before']['tentative']!=e['teacher_label'];a['revisit_was_wrong']+=int(wrong);a['revisit_immediately_fixed']+=int(wrong and e['after']['tentative']==e['teacher_label'])
rows=[{'size':k[0],'world':k[1],'strategy':k[2],**v} for k,v in aggregate.items()]
write(ROOT/'verification/RELAPSE_AUDIT.json',{'post_hoc_diagnostic_not_used_for_selection_or_configuration':True,
    'caution':'Eligibility here uses scores immediately after D; later queries can change these scores. Actual later query membership is also checked. Repeated acquisition seeds are not independent datasets.',
    'rows':rows,'details':details});print(json.dumps(rows,indent=2))
