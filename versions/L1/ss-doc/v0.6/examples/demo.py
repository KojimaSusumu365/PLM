"""Readable optional-maintenance example, not a performance comparison."""
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
from ss_reconfirm.runtime import generate
from ss_select.memory import SelectorMemory
from ss_select.runtime import Workset,choose
from ss_select.feedback import answer

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);model=PartialModel.load(ROOT/'model');selector=SelectorMemory.load(ROOT/'data/selector_model')
    text='太郎が花子を助けた。その後、由紀が健太を褒めた。';packet=read(model,[text])['packet']
    a='event:1/subject';b='event:1/object';scope={'episode':'selection-readable-06','mutable':[a,b]}
    memory=RevisionMemory(model.codec.candidates,'versioned_pair','readable-select-06');begin(model,memory,scope,packet)
    for t,v in ((a,'entity:由紀'),(b,'entity:健太')):teach(model,memory,scope,packet,request(model,memory,scope,packet,t,v))
    o=copy.deepcopy(model.recover(packet)['observation'])
    for t in (a,b):o['cells'][t]=cell('unobserved',[])
    fresh=model.encode(o);work=Workset(model,[{'id':'readable','scope':scope,'packet':fresh}]);memory.save(out/'before-memory')
    write(out/'workset.json',work.entries);write(out/'scope.json',scope);write(out/'fresh-packet.json',fresh)
    pick=choose(memory,work,selector=selector);q=pick['question'];value='entity:由紀' if q['target']==a else 'entity:健太'
    write(out/'answer.json',{'question':q,'value':value});receipt=answer(model,memory,work,q,value);memory.save(out/'after-memory')
    loaded=RevisionMemory.load(out/'after-memory',model.codec.candidates);s=Session(model,loaded,scope,fresh);assert s.confirmed=={}
    s.save(out/'cold-session.json');g=generate(model,loaded,s);assert g['text']==text
    result={'passed':True,'scope':'Readable optional maintenance only. Existing memory already supports both targets; no delayed background in this small example.',
            'selection':pick,'external_answer':value,'receipt':receipt,'cold_generation':g,'confirmations':1,'no_session_receipts':True,'eligible_for_inference':False}
    write(out/'DEMO.json',result);print(json.dumps({'passed':True,'question':q['prompt'],'optional':not q['required_now'],'generated':g['text']},ensure_ascii=False))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
