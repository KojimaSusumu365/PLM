"""Post-hoc safety characterization; never used to tune the frozen primary experiment."""
import itertools
import json
import random
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,sha
from ss_multicode.algebra import digest
from ss_trace.runtime import State,choice,TRACE_MARGIN
from ss_trace.learning import teach


def main():
    plan={'post_hoc':True,'loads':[32,128,512],'seeds':[f'active3-stress-{i}' for i in range(4)],
          'arms':['main512_pair','main512_bank'],'revision_count':16,
          'purpose':'Characterize trace saturation and teacher revision, not select settings or replace the primary endpoint.',
          'script_sha256':sha(Path(__file__))}
    write(ROOT/'verification/STRESS_PLAN.json',plan)
    rows=[];arrays={};teachers=0
    for seed in plan['seeds']:
        contexts=[dict(zip(('f0','f1','f2','f3'),map(str,v))) for v in itertools.product(range(8),repeat=4)]
        random.Random(seed).shuffle(contexts)
        for n in plan['loads']:
            labels=[str(int(digest(['stress-truth',seed,c])[:8],16)%4) for c in contexts[:n]]
            for arm in plan['arms']:
                s=State(arm,seed)
                for c,y in zip(contexts[:n],labels):teach(s,c,y);teachers+=1
                for stage in ('before_revision','after_revision'):
                    if stage=='after_revision':
                        for i in range(16):
                            labels[i]=str((int(labels[i])+1)%4);teach(s,contexts[i],labels[i]);teachers+=1
                    raw=s.raw(contexts[:n]+contexts[n:n+128])[1];d=choice(raw)
                    conf=(d['accepted']>=0)&(d['margin']>=TRACE_MARGIN);truth=np.array(list(map(int,labels)))
                    key=f'{seed}_{n}_{arm}_{stage}';arrays[key]=raw
                    s.save(ROOT/'verification/stress_states'/key)
                    rows.append({'seed':seed,'load':n,'arm':arm,'stage':stage,'array':key,'state':'verification/stress_states/'+key,
                                 'contexts':contexts[:n]+contexts[n:n+128],'last_teacher':list(labels),
                                 'confident_correct':int((conf[:n]&(d['accepted'][:n]==truth)).sum()),
                                 'confident_wrong':int((conf[:n]&(d['accepted'][:n]!=truth)).sum()),
                                 'not_confident':int((~conf[:n]).sum()),
                                 'revised16_confident_correct':int((conf[:16]&(d['accepted'][:16]==truth[:16])).sum()),
                                 'unknown_confident':int(conf[n:].sum()),'unknown_n':128})
                # Restore original external labels for the next arm; each arm starts from the same stream.
                labels=[str(int(digest(['stress-truth',seed,c])[:8],16)%4) for c in contexts[:n]]
    np.savez_compressed(ROOT/'verification/STRESS_SCORES.npz',**arrays)
    write(ROOT/'verification/STRESS.json',{'plan':plan,'actual_teacher_presentations':teachers,'rows':rows})
    for n in plan['loads']:
        for arm in plan['arms']:
            for stage in ('before_revision','after_revision'):
                subset=[r for r in rows if (r['load'],r['arm'],r['stage'])==(n,arm,stage)]
                print(json.dumps({'load':n,'arm':arm,'stage':stage,'n':n*len(subset),
                      **{k:sum(r[k] for r in subset) for k in ('confident_correct','confident_wrong','not_confident','revised16_confident_correct','unknown_confident','unknown_n')}},ensure_ascii=False))


if __name__=='__main__':main()
