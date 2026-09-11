import json,sys
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
from ss_core_v04.runtime import load
from ss_core_v04.memory import WorkingMemory
core=load(root);wm=WorkingMemory.load(root/'wm',core.schema,core.engine)
with np.load(root/'controls.npz',allow_pickle=False) as a:result=core.generate(wm,a['order'],a['goals'])
assert not any(k in sys.modules for k in ('ss_core_v04.boundary','ss_core_v04.compile','ss_core_v03.runtime','ss_document','ss_partial','evaluation'))
print(json.dumps({'result':result,'forbidden_modules_loaded':False},ensure_ascii=False))
