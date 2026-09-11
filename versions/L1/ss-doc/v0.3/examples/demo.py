import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.update import request
from ss_partial.contract import cell
from ss_retention.memory import CorrectionMemory
from ss_retention.learning import teach
from ss_retention.runtime import generate

def demo(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);model=PartialModel.load(ROOT/'model')
    a='太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が美咲を訪ねた。'
    b=a.replace('花子が健太','由紀が健太');p=read(model,[a,b])['packet'];episode='demonstration-episode-03';target='event:1/subject'
    memory=CorrectionMemory(model.codec.candidates,'split_pair','demo-retention-03')
    before=generate(model,memory,episode,p)
    teach(model,memory,episode,p,request(p,target,'entity:由紀'))
    for i in range(12):teach(model,memory,'different-episode-'+str(i),p,request(p,target,'entity:花子'),False)
    memory.save(out/'memory');fp=memory.fingerprint
    memory=CorrectionMemory.load(out/'memory',model.codec.candidates);assert memory.fingerprint==fp
    # Fresh observation has no target candidate at all; never reload the corrected packet.
    o=copy.deepcopy(model.recover(p)['observation']);o['cells'][target]=cell('unobserved',[]);fresh=model.encode(o)
    result=generate(model,memory,episode,fresh,'reverse');assert result['status']=='generated'
    other=generate(model,memory,'new-episode',fresh)
    record={'initial_readings':[a,b],'external_confirmation':'第二事象の主体は由紀','before':before,
            'background_teacher_presentations':12,'restart_fingerprint_equal':True,'fresh_target_state':'unobserved',
            'after_restart':result,'other_episode':other,'episode':episode,'memory_fingerprint':fp,
            'independent_primary_sample':False,'eligible_for_inference':False}
    for name,value in (('fresh-packet.json',fresh),('EXAMPLE.json',record)):
        with (out/name).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,sort_keys=True,allow_nan=False)
    return record

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out');a=p.parse_args()
    if a.out:r=demo(a.out)
    else:
        with tempfile.TemporaryDirectory(prefix='ssdoc03-demo-') as t:r=demo(Path(t)/'run')
    print(json.dumps(r,ensure_ascii=False,indent=2))
