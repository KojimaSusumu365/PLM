import argparse,copy,time
from pathlib import Path
import numpy as np
from evaluation.integrity import ROOT,read,write
from evaluation.revision_cases import prepared_data
from evaluation.delay_cases import entries
from evaluation.delay_experiment import initialize,background,slot_score,utility,branch_confirmation
from ss_partial.runtime import PartialModel
from ss_select.runtime import Workset,candidates
from ss_select.memory import SelectorMemory
from ss_select.training import fit

def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);start=time.perf_counter()
    model=PartialModel.load(ROOT/'model');data=read(ROOT/'data/DELAY_DATASETS.json');plan=read(ROOT/'evaluation/PROTOCOL.json');examples=[]
    for split in plan['selector_training_splits']:
        ds=data['splits'][split];focal=ds['cases'][:ds['focal']];records=prepared_data(model,ds['cases']);byid={r['id']:r for r in records}
        work=Workset(model,entries(model,focal));write(out/f'TEACHERS-{split}.json',records)
        for seed in plan['selector_teaching_code_seeds']:
            for method in plan['memory_methods']:
                memory=initialize(model,records,method,seed);previous=0
                for load in plan['background_levels']:
                    background(memory,records,previous,load);previous=load;future=copy.deepcopy(memory)
                    background(future,records,load,load+plan['delayed_background']);baseline=slot_score(future,focal,records);base={r['id']:r for r in baseline}
                    rows=candidates(memory,work)
                    for row in rows:
                        q=row['question'];case=next(c for c in focal if c['id']==q['id']);target=q['target'];branch=copy.deepcopy(memory)
                        branch_confirmation(branch,byid[q['id']],target,case['final']['cells'][target]['candidates'][0])
                        background(branch,records,load,load+plan['delayed_background']);after=slot_score(branch,focal,records);selected=next(r for r in after if r['id']==q['id'])
                        reward=utility(selected)-utility(base[q['id']]);assert -2<=reward<=2
                        examples.append({'split':split,'content_code':seed,'method':method,'load':load,'id':q['id'],'target':target,
                            'features':row['features'],'reward':reward,'baseline_local':base[q['id']],'after_local':selected,
                            'global_correct_change':sum(r['correct'] for r in after)-sum(r['correct'] for r in baseline),
                            'global_wrong_change':sum(r['wrong'] for r in after)-sum(r['wrong'] for r in baseline),
                            'counterfactual_confirmations':1,'delayed_background':plan['delayed_background'],'eligible_for_inference':False})
                    print({'training':split,'seed':seed,'method':method,'load':load,'examples':len(examples)},flush=True)
    selector=SelectorMemory();loss=fit(selector,examples,plan['selector_epochs']);selector.save(out/'model');pred=[selector.predict(x['features']) for x in examples]
    write(out/'EXAMPLES.json',examples);write(out/'TRAINING.json',{'examples':len(examples),'counterfactual_answers':len(examples),
          'epochs':plan['selector_epochs'],'epoch_online_mse':loss,'final_training_mse':float(np.mean([(p-x['reward'])**2 for p,x in zip(pred,examples)])),
          'rewards':{str(v):sum(x['reward']==v for x in examples) for v in sorted({x['reward'] for x in examples})},
          'cost':selector.cost(),'model_fingerprint':selector.fingerprint,'eligible_for_inference':False})
    write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-start});print({'trained':True,'examples':len(examples),'fingerprint':selector.fingerprint},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
