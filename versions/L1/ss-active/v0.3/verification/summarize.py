"""Descriptive aggregation only. Does not alter frozen settings or runtime."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write


def add(target, source):
    for k,v in source.items():
        if k in ('precision','recall'):continue
        if isinstance(v,dict):add(target.setdefault(k,{}),v)
        elif type(v) in (int,float):target[k]=target.get(k,0)+v


def ratios(obj):
    for v in list(obj.values()):
        if isinstance(v,dict):ratios(v)
    if {'tp','fp','fn','tn'} <= set(obj):
        obj['precision']=obj['tp']/(obj['tp']+obj['fp']) if obj['tp']+obj['fp'] else None
        obj['recall']=obj['tp']/(obj['tp']+obj['fn']) if obj['tp']+obj['fn'] else None


def main():
    ev=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'));groups={};paired=[]
    for run in ev['runs']:
        for cp in run['checkpoints']:
            key=(run['size'],run['world'],run['arm'],cp['name'])
            a=groups.setdefault(key,{'runs':0,'metrics':{}});a['runs']+=1;add(a['metrics'],cp['metrics'])
            if cp['name'] in ('post_D','post_E'):
                c=cp['metrics']['cohorts']['immediately_correct']
                for detector in ('ss_disagreement','ss_weak_support'):
                    x=c['detectors'][detector]['last_teacher'];b=c['detectors']['gap_drop']['last_teacher']
                    paired.append({'base_id':run['base_id'],'data_seed':run['data_seed'],'size':run['size'],'world':run['world'],
                                   'arm':run['arm'],'checkpoint':cp['name'],'detector':detector,
                                   'tp_delta_vs_gap':x['tp']-b['tp'],'fp_delta_vs_gap':x['fp']-b['fp']})
    rows=[]
    for (size,world,arm,cp),v in sorted(groups.items()):
        ratios(v['metrics']);rows.append({'size':size,'world':world,'arm':arm,'checkpoint':cp,**v})
    write(ROOT/'verification/SUMMARY.json',{'rows':rows,'paired_deltas':paired,
         'scope':'Descriptive paired counts. Per cell8 crossed data/code runs from4 datasets; cohorts/checkpoints overlap.'})
    for row in rows:
        if row['checkpoint']=='post_E' and row['arm'] in ('main512','main512_pair','main384_pair','main512_bank','main640'):
            m=row['metrics'];print(json.dumps({k:row[k] for k in ('size','world','arm')}|{'old':m['old'],
                 'cohort':m['cohorts']['immediately_correct'],'first_corrected':m['cohorts']['first_corrected'],
                 'unknown_trace':m['unknown_trace']},ensure_ascii=False))


if __name__=='__main__':main()
