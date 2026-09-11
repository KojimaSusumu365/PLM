import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'PLM-S1-v0.2'))
import plm_s1_v02
import numpy as np
from plm_p1.core import PhaseCodebook,encode
from plm_p1_v02.fixtures import make_frames
from plm_s1_v02.link import Link,transmit,simulate_channel
from plm_s1_v02.receiver import synchronize

for keep in (1.,.25):
    for layout in ('distributed4','edge2'):
        book=PhaseCodebook(2048,'s1-v02-code-53101')
        link=Link(layout=layout)
        tx,norm=transmit(encode(make_frames(4),book),book,link)
        for f in (-4.5,-3.,-2.05,-1.9,-1.061538,-.480769,0.,.480769,1.061538,1.9,2.05,3.,4.5,8.,16.):
            y,m=simulate_channel(tx,link,seed=62101,phase_rad=1.8,cfo_hz=f,delay_chips=-5,keep_fraction=keep,noise_std=.25,jitter_std=.03)
            a,obs,s=synchronize(y,m,book,link,norm)
            print(keep,layout,f,s['status'],s['estimated_cfo_hz'],s['reason'],s['joint_coherence'],s['frequency_score_gap'])
