"""Small, separately labelled demonstration; not primary evaluation data."""
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.contract import cell
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin,request,teach
from ss_reconfirm.session import Session
from ss_reconfirm.runtime import assess,generate
from ss_reconfirm.learning import confirm

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);model=PartialModel.load(ROOT/'model')
    text='太郎が花子を助けた。その後、由紀が健太を褒めた。'
    packet=read(model,[text])['packet'];a='event:1/subject';b='event:1/object'
    scope={'episode':'v05-readable-demonstration','mutable':[a,b]}
    m=RevisionMemory(model.codec.candidates,'versioned_pair','readable-demo-05');begin(model,m,scope,packet)
    for t,v in ((a,'entity:由紀'),(b,'entity:健太')):teach(model,m,scope,packet,request(model,m,scope,packet,t,v))
    original=copy.deepcopy(model.recover(packet)['observation']);o=copy.deepcopy(original)
    o['cells'][a]=cell('known',['entity:花子']);o['cells'][b]=cell('unobserved',[])
    input_packet=model.encode(o);s=Session(model,m,scope,input_packet);initial=assess(model,m,s)
    assert initial['status']=='needs_confirmation' and [q['target'] for q in initial['questions']]==[a]
    m.save(out/'before-memory');s.save(out/'before-session.json');write(out/'scope.json',scope);write(out/'input-packet.json',input_packet)
    q=initial['questions'][0];answer={'question':q,'value':'entity:由紀'};write(out/'answer.json',answer)
    s,receipt=confirm(model,m,s,q,answer['value']);immediate=generate(model,m,s);assert immediate['text']==text
    m.save(out/'after-memory');s.save(out/'after-session.json')
    m=RevisionMemory.load(out/'after-memory',model.codec.candidates)
    for t in (a,b):original['cells'][t]=cell('unobserved',[])
    fresh=model.encode(original);cold=Session(model,m,scope,fresh);assert cold.confirmed=={}
    cold.save(out/'cold-session.json');write(out/'cold-packet.json',fresh)
    recalled=generate(model,m,cold);assert recalled['text']==text
    result={'status':'passed','scope':'Small illustrative example, not an additional primary test.',
            'input_description':'事象2の主体は古い既知値「花子」、対象は未観測。現在のSS記憶は主体「由紀」、対象「健太」。',
            'initial_plan':initial,'external_answer':answer,'receipt':receipt,'immediate':immediate,'cold_without_receipts':recalled,
            'teacher_confirmations':1,'cold_teacher_confirmations':0,'eligible_for_inference':False}
    write(out/'DEMO.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
