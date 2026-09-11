import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parent.parent/"outputs"/"PLM-L1-v0.6"
sys.path.insert(0,str(ROOT))
from plm_l1_v06.banked import fit_banked,MODES

start=time.perf_counter()
for dimension in (128,512,2048):
    for load in (32,128,256):
        obs=[({"address":f"dev:{i}"},f"label:{i%8}") for i in range(load)]
        for mode in MODES:
            mem,stats=fit_banked(obs,dimension,"banked-development-0",partial=False,mode=mode,cache_slots=0)
            correct=wrong=abstain=missing=0
            for key,target in obs:
                out=mem.recall(key)["value"]
                correct+=out==target
                wrong+=out is not None and out!=target
                abstain+=out is None
            for i in range(128):
                missing+=mem.recall({"address":f"absent-dev:{i}"})["value"] is not None
            print(json.dumps({"dimension":dimension,"load":load,"mode":mode,"correct":correct,"wrong":wrong,"abstain":abstain,"missing_false":missing,"banks":stats["bank_counts"],"owned_bytes":stats["owned_heap_bytes"]}),flush=True)
print("ELAPSED",time.perf_counter()-start)
