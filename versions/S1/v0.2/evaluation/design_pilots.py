"""Deterministic aperture selection; no codebooks, frames, channel/evaluation seeds."""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    frequency=np.arange(.40,22.001,.01)
    block=np.abs(np.sin(np.pi*frequency*64/8000)/(64*np.sin(np.pi*frequency/8000)))
    candidates=[]
    for a in range(900,3600,100):
        for b in range(4400,7500,100):
            starts=np.array([16,a,b,8400])
            response=np.abs(np.exp(2j*np.pi*frequency[:,None]*starts/8000).mean(axis=1))*block
            candidates.append({'starts':starts.tolist(),'near_sidelobe_max':float(response[frequency<=6].max()),'far_sidelobe_max':float(response.max())})
    selected=min((r for r in candidates if r['near_sidelobe_max']<=.80),key=lambda r:(r['far_sidelobe_max'],r['starts']))
    result={'scope':'noiseless all-pilot observation frequency-aperture calculation; not a guarantee under erasures/noise',
            'rule':'among near (0.40..6 Hz) sidelobes <=0.80 minimize maximum sampled sidelobe over 0.40..22 Hz; step 0.01 Hz; deterministic starts tie-break',
            'candidate_count':len(candidates),'selected':selected,'candidates':candidates}
    with Path(args.out).open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
    print(json.dumps({'candidate_count':len(candidates),'selected':selected},indent=2))


if __name__=='__main__': main()
