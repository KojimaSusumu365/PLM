import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
from ss_partial.runtime import PartialModel
from ss_partial.reader import read as interpret
from ss_partial.contract import cell
from ss_revision.memory import RevisionMemory
from ss_revision.learning import request

def run(work):
    verify();work=Path(work).resolve();work.mkdir(parents=True,exist_ok=False)
    model=PartialModel.load(ROOT/'model');a,b='event:1/subject','event:1/object'
    scope={'episode':'cli-workflow-04','mutable':[a,b]};write(work/'scope.json',scope)
    text='太郎が花子を助けた。その後、由紀が健太を褒めた。'
    packet=interpret(model,[text,text.replace('由紀が','花子が')])['packet'];write(work/'packet0.json',packet);commands=[]
    def call(args,ok=True):
        cmd=[sys.executable,'-B','-m','ss_revision',*map(str,args)];p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        assert (p.returncode==0)==ok,p.stderr
        commands.append({'command':cmd,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});return p
    call(['init','--model',ROOT/'model','--out',work/'empty'])
    call(['open','--model',ROOT/'model','--memory',work/'empty','--scope',work/'scope.json','--packet',work/'packet0.json','--out',work/'opened'])
    previous=work/'opened';source=work/'packet0.json'
    for i,(target,value,op) in enumerate(((a,'entity:由紀','supply'),(b,'entity:次郎','revise'),(a,'entity:美咲','revise')),1):
        m=RevisionMemory.load(previous,model.codec.candidates);msg=request(model,m,scope,read(source),target,value,op);write(work/f'message{i}.json',msg)
        call(['teach','--model',ROOT/'model','--memory',previous,'--scope',work/'scope.json','--packet',source,'--message',work/f'message{i}.json','--out',work/f'memory{i}','--packet-out',work/f'packet{i}.json'])
        previous=work/f'memory{i}';source=work/f'packet{i}.json'
    obs=model.recover(read(source))['observation']
    for target in (a,b):obs['cells'][target]=cell('unobserved',[])
    write(work/'fresh.json',model.encode(obs))
    p=call(['generate','--model',ROOT/'model','--memory',previous,'--scope',work/'scope.json','--packet',work/'fresh.json','--order','reverse'])
    assert json.loads(p.stdout)['text']=='美咲が次郎を褒めた。その前に、太郎が花子を助けた。'
    m=RevisionMemory.load(previous,model.codec.candidates);fp=m.fingerprint
    stale=request(model,m,scope,read(source),a,'entity:由紀','revise');stale.update(base_revision=0,revision=1);write(work/'stale.json',stale)
    p=call(['teach','--model',ROOT/'model','--memory',previous,'--scope',work/'scope.json','--packet',source,'--message',work/'stale.json','--out',work/'forbidden-memory','--packet-out',work/'forbidden-packet.json'],False)
    assert 'stale_or_out_of_order_confirmation' in p.stderr
    assert not (work/'forbidden-memory').exists() and not (work/'forbidden-packet.json').exists()
    assert RevisionMemory.load(previous,model.codec.candidates).fingerprint==fp
    write(ROOT/'verification/CLI_WORKFLOW.json',{'passed':True,'commands':commands,'stale_outputs_absent':True,'memory_unchanged_after_rejection':True})
    print({'passed':True,'commands':len(commands)},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',required=True);a=p.parse_args();run(a.work)
