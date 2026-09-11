"""Signal-only aperture search, no evaluation seeds/frames/labels."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import numpy as np

freq=np.arange(.40,22.001,.01)
block=np.abs(np.sin(np.pi*freq*64/8000)/(64*np.sin(np.pi*freq/8000)))
results=[]
for a in range(900,3600,100):
    for b in range(4400,7500,100):
        starts=np.array([16,a,b,8400])
        response=np.abs(np.exp(2j*np.pi*freq[:,None]*starts/8000).mean(axis=1))*block
        near=float(response[freq<=6].max())
        far=float(response.max())
        results.append((far,near,a,b))
for row in sorted(results)[:12]: print(row)
