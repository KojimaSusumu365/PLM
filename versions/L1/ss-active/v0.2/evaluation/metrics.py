import numpy as np
from ss_multicode.model import decide,policy
from ss_active.selection import context_id
from .cases import truth_map


def decisions(scores):return decide({'readers':np.asarray(scores),'checker':np.empty((len(scores),0))},policy())


def probes(case):return [r for g in 'ABCDE' for r in case['groups'][g]]+[{'id':context_id(c),'context':c} for c in case['unknown']]


def summarize(scores,case,world,known_groups,selected,baseline,control,corrected,first_corrected,post_d_relapsed):
    rows=probes(case);ids=[r['id'] for r in rows];truth=truth_map(case,world);ys=np.array([int(truth.get(k,'-1')) for k in ids]);g=case['size']
    pool={r['id'] for r in case['pool']};selected=set(selected);changed=set(case['changed_ids']) if world=='changed_pool16' else set()
    groups={k:np.arange(i*g,(i+1)*g) for i,k in enumerate('ABCDE')}
    domains={'old_all':set(ids[:2*g]),'pool':pool,'pool_selected':selected,'pool_unselected':pool-selected,
             'protected_old':set(ids[:2*g])-pool,'changed_pool':changed,'old_stable':set(ids[:2*g])-changed,'never_taught':set(ids[5*g:]),
             'ever_directly_corrected':set(corrected),'first_block_corrected':set(first_corrected),'post_D_relapsed_first_block':set(post_d_relapsed)}
    groups.update({k:np.array([i for i,x in enumerate(ids) if x in keys],dtype=int) for k,keys in domains.items()})
    current=decisions(scores);base=decisions(baseline);ct=decisions(control);known=np.arange(len(rows))<known_groups*g;was_known=np.arange(len(rows))<3*g;out={}
    for name,ix in groups.items():
        m={'requests':len(ix),'known_requests':int(known[ix].sum()),'unseen_requests':int((~known[ix]).sum())};tr={}
        for field in ('tentative','accepted'):
            x=current[field][ix];m[field+'_correct']=int((known[ix]&(x==ys[ix])).sum());m[field+'_wrong']=int((known[ix]&(x>=0)&(x!=ys[ix])).sum());m[field+'_abstained']=int((known[ix]&(x<0)).sum())
            bc=(base[field][ix]==ys[ix])&was_known[ix];cc=(x==ys[ix])&was_known[ix]
            tr[field+'_baseline_correct']=int(bc.sum());tr[field+'_newly_correct']=int((cc&~bc).sum());tr[field+'_lost_baseline_correct']=int((bc&~cc).sum())
            m[field+'_correct_no_acquisition_control']=int((known[ix]&(ct[field][ix]==ys[ix])).sum())
        m['unseen_false_accept']=int(((~known[ix])&(current['accepted'][ix]>=0)).sum());m['unseen_rejected']=m['unseen_requests']-m['unseen_false_accept'];m['transitions']=tr;out[name]=m
    return {'groups':out}
