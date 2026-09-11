import copy,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.contract import cell
from ss_revision.memory import RevisionMemory
from ss_revision.learning import begin,request,teach
from ss_revision.runtime import generate

def demo(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    model=PartialModel.load(ROOT/'model');a,b='event:1/subject','event:1/object'
    scope={'episode':'revision-demonstration-04','mutable':[a,b]}
    texts=['太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が美咲を訪ねた。',
           '太郎が花子を助けた。その後、由紀が健太を褒めた。その後、健太が美咲を訪ねた。']
    packet=read(model,texts)['packet'];memory=RevisionMemory(model.codec.candidates,'versioned_pair','revision-demo-04');root=begin(model,memory,scope,packet)
    steps=[]
    for target,value,op in ((a,'entity:由紀','supply'),(b,'entity:次郎','revise'),(a,'entity:美咲','revise'),(b,'entity:太郎','revise'),(a,'entity:由紀','revise')):
        msg=request(model,memory,scope,packet,target,value,op);r=teach(model,memory,scope,packet,msg);packet=r['packet']
        o=copy.deepcopy(model.recover(packet)['observation'])
        for t,v in memory.roots[root]['versions'].items():
            if v:o['cells'][t]=cell('unobserved',[])
        g=generate(model,memory,scope,model.encode(o),'reverse');assert g['status']=='generated'
        steps.append({'confirmation':msg,'local_audit':r['local_audit'],'generated':g['text']})
    for i in range(20):
        other={**scope,'episode':'revision-demo-background-'+str(i)};begin(model,memory,other,packet,False)
        teach(model,memory,other,packet,request(model,memory,other,packet,a,'entity:花子','revise'))
    memory.save(out/'memory');new=RevisionMemory.load(out/'memory',model.codec.candidates);assert new.fingerprint==memory.fingerprint
    o=copy.deepcopy(model.recover(packet)['observation'])
    for target in (a,b):o['cells'][target]=cell('unobserved',[])
    fresh=model.encode(o);result=generate(model,new,scope,fresh,'reverse');assert result['status']=='generated'
    msg=request(model,new,scope,packet,a,'entity:美咲','revise');msg.update(base_revision=1,revision=2);fp=new.fingerprint
    try:teach(model,new,scope,packet,msg);raise AssertionError('stale accepted')
    except ValueError as e:reason=str(e)
    assert reason=='stale_or_out_of_order_confirmation' and new.fingerprint==fp
    record={'initial_readings':texts,'scope':scope,'steps':steps,'background_confirmations':20,'after_restart':result,
            'stale_rebound_rejected':reason,'memory_unchanged_after_rejection':True,
            'not_independent_primary_sample':True,'eligible_for_inference':False}
    for name,value in (('scope.json',scope),('fresh-packet.json',fresh),('EXAMPLE.json',record)):
        with (out/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,allow_nan=False,sort_keys=True)
    return record

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='ssdoc04-demo-') as folder:
        print(json.dumps(demo(Path(folder)/'run'),ensure_ascii=False,indent=2))
