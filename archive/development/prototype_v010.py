import sys,time,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs/PLM-L1-v0.10'; sys.path.insert(0,str(root))
from evaluation.support import data,parse
from plm_l1_v010.training import fit
from plm_l1_v010.memory import fit_memory

for mode in ('standard','confounded','resolved'):
    train=data('component_train'); val=data('single_development')
    if mode!='standard':
        def confounded(r): return (r['meaning']['polarity']=='polarity:negative')==(r['meaning']['modality']=='modality:hypothetical')
        train=[r for r in train if confounded(r)]; val=[r for r in val if confounded(r)]
        if mode=='resolved':
            texts=('太郎が花子を助けなかった。','もし太郎が花子を助けたら。')
            train += [r for r in data('component_train') if r['text'] in texts]
    start=time.perf_counter(); model=fit(train,val,data('temporal_train'),data('lexicon'))
    print(mode,'members',len(model.members),'supported',model.meta['training']['supported'],'time',time.perf_counter()-start,flush=True)
    print(model.meta['training']['selected_masks'],flush=True)
    for text in ('太郎が花子を助けた。その後、花子が健太を褒めた。','太郎が花子を助けなかった。その後、花子が健太を褒めた。'):
        out=model.read(text); print('read',text,out['status'],out.get('reason'),flush=True)
    meaning=data('development')[0]['meaning']; meaning['events'][0]['polarity']='polarity:negative'; meaning['events'][0]['modality']='modality:asserted'
    out=model.generate(model.encode(meaning)); print('generate',json.dumps(out,ensure_ascii=False),flush=True)
    if mode=='standard':
        for n,a in model.selection_audit.items(): print(n,'supported',a['supported'],'pool',a['plausible_minimal_count'],flush=True)
