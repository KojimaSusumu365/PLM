"""Read-only replay of packaged demonstration waveforms and independently scored texts."""
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify
from evaluation.oracle import scored,localize
from ss_partial.runtime import PartialModel
from ss_core_v02.store import Store,scope_id
from ss_core.clock import ReadWindow

def main(out):
    frozen=verify();p=ROOT/'examples/reconfirmation';model=PartialModel.load(ROOT/'model')
    c=read(p/'SOURCE.json');initial=Store.load(p/'initial-store',model.codec.candidates)
    held=Store.load(p/'held-store',model.codec.candidates);confirmed=Store.load(p/'confirmed-store',model.codec.candidates)
    assert initial.memory.fingerprint==held.memory.fingerprint and scope_id(c['scope']) in held.pending
    assert not confirmed.pending
    logs=read(p/'WINDOWS.json');replayed=[]
    with np.load(p/'noisy-read-windows.npz',allow_pickle=False) as z:
        for i,log in enumerate(logs):
            part=next(p for p in initial.memory.ss.parts.values() if p.seed==log['part_seed'])
            w=ReadWindow(part,log['key'],log['nonce'],True)
            for tick,(y,mask) in enumerate(zip(z[f'window{i}_samples'],z[f'window{i}_observed'])):w.push(tick,y,mask)
            scores,audit=w.finish();assert scores.tolist()==log['scores'] and audit==log['audit'];replayed.append(scores)
    observed=float(np.sqrt(np.mean((replayed[0]-replayed[1])**2)))
    receipt=read(p/'HELD_UPDATE.json');reported=receipt['receipts'][0]['memory_update']['windows']['main']['pre_score_rms']
    assert observed==reported and observed>0.15
    for order,goals in [('preserve',['subject','subject']),('reverse',['object','subject'])]:
        r=read(p/(order+'-GENERATE.json'));ids=c['meaning']['presentation'][::1 if order=='preserve' else -1]
        assert all(scored(localize(c['meaning'],ids,goals),r['text']).values())
    write(out,{'passed':True,'frozen_digest':frozen,'waveforms_replayed':len(logs),'correct_output_texts':2,
               'held_ss_memory_unchanged':True,'pending_cleared_after_external_reconfirmation':True,
               'pre_score_rms':observed})
    print({'examples_verified':True,'recorded_pre_score_rms':observed},flush=True)

if __name__=='__main__':main(sys.argv[1])
