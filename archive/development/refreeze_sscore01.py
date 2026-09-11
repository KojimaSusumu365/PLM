import sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent/'outputs/PLM-L1-SS-core-v0.1'
sys.path.insert(0,str(R))
from evaluation.integrity import read,sources,freeze,write
old=read(R/'verification/INITIAL_FREEZE.json')['files']
now=sources()
changed=[p for p in old if old[p]!=now.get(p)]
assert set(changed)=={'evaluate.py','evaluation/experiment.py','verify_release.py'} and set(old)==set(now),changed
final=freeze()
write(R/'verification/AMENDMENT_DIFF.json',{'changed_paths':changed,
    'before':{p:old[p] for p in changed},'after':{p:now[p] for p in changed},
    'final_frozen_digest':final,'core_data_protocol_unchanged':True})
print({'frozen':final,'only_harness_files_changed':changed})
