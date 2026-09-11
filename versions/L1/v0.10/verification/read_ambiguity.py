"""Posthoc reading diagnostic; uses frozen models without any refit or tuning."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.support import render_event,expected,to_mentions
from evaluation.metrics import score
from plm_l1_v010.runtime import CommitteeModel

def render(m):
    w=expected(m,('subject','subject'))
    marker={'unknown':'','before':'その後、','after':'その前に、'}[w['relation']]
    return render_event(w['events'][0],'subject')+marker+render_event(w['events'][1],'subject')

def main():
    result=json.loads((ROOT/'results/EVALUATION.json').read_text(encoding='utf-8'))
    rows=result['language_ambiguity']['ss_multi/before']['details'];reports={}
    for stage in ('before','after'):
        model=CommitteeModel.load(ROOT/'results'/('ambiguity-'+stage))
        for kind in ('crossed_status','previously_correlated'):
            predictions=[];gold=[];details=[]
            for row in rows:
                m=json.loads(json.dumps(row['meaning']))
                if kind=='previously_correlated':
                    for e in m['events']:e['polarity']='polarity:positive';e['modality']='modality:asserted'
                text=render(m);out=model.read(text)
                value=model.recover(out['packet']).get('meaning') if out['status']=='read' else None
                predictions.append(value);gold.append(to_mentions(m))
                details.append({'text':text,'status':out['status'],'reason':out.get('reason'),'meaning':value,
                                'packet_emitted':out.get('packet') is not None,'correct':value==gold[-1]})
            reports[stage+'/'+kind]={'metrics':score(predictions,gold),'unique_texts':len({d['text'] for d in details}),
                                   'model_fingerprint':model.fingerprint,'details':details}
    record={'scope':'Posthoc diagnostic on frozen saved models, using the independent evaluation renderer. Not used for tuning or primary acceptance.',
            'reports':reports}
    with (ROOT/'verification/READ_AMBIGUITY.json').open('x',encoding='utf-8') as f:
        f.write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:{'metrics':v['metrics'],'unique_texts':v['unique_texts']} for k,v in reports.items()},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
