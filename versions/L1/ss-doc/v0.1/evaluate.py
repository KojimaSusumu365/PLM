import argparse
import json
import time
from pathlib import Path
import numpy as np
from ss_document.training import train,variant
from evaluation.integrity import ROOT,read,write,verify
from evaluation.cases import corpus,INVALID,scene_key
from evaluation.experiment import trial,adapt_legacy,disturbances


def run(out):
    locked=verify();out=Path(out);out.mkdir(parents=True,exist_ok=False);t0=time.perf_counter()
    base=train(read(ROOT/'data/component_train.json'),read(ROOT/'data/temporal_train.json'),read(ROOT/'data/lexicon.json')).base
    cases=corpus('evaluation',12);development=corpus('development',4)
    assert len(cases)==144 and len({c['text'] for c in cases})==144
    assert not {scene_key(c['meaning']['events']) for c in cases}&{scene_key(c['meaning']['events']) for c in development}
    write(out/'CASES.json',cases);write(out/'DEVELOPMENT_CASES.json',development)
    subset=[r for n in (2,3) for r in [c for c in cases if len(c['meaning']['events'])==n][:6]]
    rows=[];arrays={};models=[];timing=[];probes=[];regressions=[]
    for si in range(3):
        seed=f'ssdoc-code-{si}'
        configs=[(8192,'bound','normal','primary'),(1024,'bound','normal','diagnostic'),(128,'bound','normal','diagnostic'),
                 (8192,'unbound_events','normal','diagnostic'),(8192,'undirected_time','normal','diagnostic'),
                 (8192,'bound','zero_temporal_read','diagnostic'),(8192,'bound','zero_temporal_write','diagnostic'),
                 (8192,'bound','zero_lexical_write','diagnostic')]
        for ci,(dimension,mode,condition,stage) in enumerate(configs):
            model=variant(base,dimension,seed,mode,condition);mid=f's{si}-c{ci}';model.save(out/'models'/mid)
            models.append({'id':mid,'seed':seed,'dimension':dimension,'mode':mode,'condition':condition,'stage':stage,
                           'fingerprint':model.fingerprint,'base_fingerprint':model.base.fingerprint,'codec_storage':model.codec.storage(),
                           'base_memories':{k:v.storage() for k,v in model.base.memories.items()},
                           'component_memories':{k:v.storage() for k,v in model.base.component.memories.items()}})
            start=time.perf_counter()
            for i,case in enumerate(cases if stage=='primary' else subset):
                row,signals=trial(model,case,stage=='primary');prefix=f'{mid}-{i:03d}'
                for key,value in signals.items():arrays[prefix+'-'+key]=value
                rows.append({'model_id':mid,'stage':stage,'array_prefix':prefix,**row})
            if stage=='primary':
                invalid=[{'text':text,'result':model.read(text)} for text in INVALID]
                m=next(c['meaning'] for c in cases if len(c['meaning']['events'])==3)
                noise,signals=disturbances(model,m,900+si)
                for key,value in signals.items():arrays[mid+'-probe-'+key]=value
                probes.append({'model_id':mid,'invalid':invalid,'signals':noise})
                if si==0:
                    for i,old in enumerate(read(ROOT/'data/evaluation.json')):
                        case={'id':old['id'],'text':old['text'],'meaning':adapt_legacy(old['meaning'])}
                        r,_=trial(model,case,False);regressions.append(r)
            timing.append({'model_id':mid,'seconds':time.perf_counter()-start})
            print(f'Completed {mid} {stage}: {len(rows)} input evaluations',flush=True)
    np.savez_compressed(out/'SIGNALS.npz',**arrays)
    result={'experiment':'PLM-L1-SS-doc-v0.1','freeze':locked,'models':models,'rows':rows,'probes':probes,
            'legacy_regression':regressions,'eligible_for_inference':False}
    write(out/'EVALUATION.json',result);write(out/'PERFORMANCE.json',{'seconds':time.perf_counter()-t0,'models':timing})
    print(json.dumps({'inputs':len(rows),'primary':sum(r['stage']=='primary' for r in rows),'legacy':len(regressions),'arrays':len(arrays)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();run(a.out)
