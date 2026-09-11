import json,platform,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify,sha
from evaluation.experiment import compact
from bridge.carrier import demodulate
from bridge.recovery import recover_masked
from ss_partial.runtime import PartialModel

def run():
    index=read(ROOT/'results/INDEX.json');rows=[read(ROOT/'results/runs'/n/'RESULT.json') for n in index['runs']];assert len(rows)==388
    plan=read(ROOT/'evaluation/PROTOCOL.json');main=[r for r in rows if r['condition'] in plan['main_conditions']];assert len(main)==360
    pairs={};generated=wrong=correct=0
    for r in rows:
        if r['method'] in ('ss_estimated','ss_disabled','ss_oracle'):
            key=(r['case_id'],r['condition'],r['channel_seed']);pairs.setdefault(key,[]).append((r['teacher_wire_sha256'],r['query_wire_sha256']))
        assert r['result']['fresh_session_no_receipts'] and not r['result']['nonmutable_changed']
        if r['teacher_learned']:
            assert len(r['teacher']['receipts'])==2
            assert all(t['local_audit']['other_cells_unchanged'] and t['local_audit']['local_numeric_delta_only'] for t in r['teacher']['receipts'])
        for o in r['result']['outputs']:
            if o['generation']['status']=='generated':
                generated+=1;wrong+=int(not all(o['score'].values()) or not o['reread_equal'])
        correct+=int(r['result']['correct'])
    assert all(len(set(v))==1 for v in pairs.values())
    parts=[r for r in main if r['condition']=='partial25' and r['method']=='ss_estimated']
    observed=[r['query']['observed_components'] for r in parts]
    model=PartialModel.load(ROOT/'model');arrays=0
    with np.load(ROOT/'examples/run/REFERENCE_SIGNALS.npz',allow_pickle=False) as reference:
        for i in (0,1):
            folder=ROOT/f'examples/run/case{i}';source=read(folder/'source.json')
            for kind,meaning in (('teacher',source['known']),('query',source['query'])):
                wire=read(folder/f'{kind}-received.json');v,m,_=demodulate(model,wire,wire['message_id']);p,_=recover_masked(model,v,m)
                for name,a in {'source':model.vector(model.encode(meaning)),'despread':v,'mask':m,'recovered':model.vector(p)}.items():
                    np.testing.assert_array_equal(a,reference[f'case{i}-{kind}-{name}']);arrays+=1
        assert arrays==len(reference.files)==16
    record={'passed':True,'runs':len(rows),'main_runs':len(main),'stress_runs':len(rows)-len(main),'independent_evaluation_scenes':12,
        'generated_documents':correct,'generated_outputs':generated,'wrong_outputs':wrong,'held_documents':sum(r['result']['status']=='held' for r in rows),
        'requested_outputs':776,'paired_ss_waveforms_equal':True,'paired_sets':len(pairs),'actual_confirmed_targets':2*sum(r['teacher_learned'] for r in rows),
        'partial25_query_observed_components':{'minimum':min(observed),'maximum':max(observed),'mean':float(np.mean(observed)),
            'mean_fraction':float(np.mean(observed)/8192)},'reference_arrays_exact':arrays,'frozen_digest':verify(),'eligible_for_inference':False}
    write(ROOT/'verification/LOG_AUDIT.json',record)
    write(ROOT/'verification/ENVIRONMENT.json',{'python':sys.version,'numpy':np.__version__,'platform':platform.platform(),
        'thread_setting':'OPENBLAS_NUM_THREADS=1','evaluation_seconds':read(ROOT/'results/PERFORMANCE.json')['seconds'],
        'scope':'Wall time includes all evaluation and persistence while a full repeat ran concurrently; not real-time or RF throughput.'})
    print(json.dumps(record,indent=2),flush=True)
if __name__=='__main__':run()
