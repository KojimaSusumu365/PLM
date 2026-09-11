"""Archive initial freeze before a harness-only held-input handling amendment."""
import shutil
import sys
from pathlib import Path
W=Path(__file__).resolve().parent.parent
R=W/'outputs/PLM-L1-SS-core-v0.1'
sys.path.insert(0,str(R))
from evaluation.integrity import verify,write
frozen=verify()
target=R/'verification/initial_harness'
target.mkdir(exist_ok=False)
for name in ('evaluate.py','evaluation/experiment.py','verify_release.py','evaluation/FREEZE.json'):
    dest=target/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(R/name,dest)
write(R/'verification/AMENDMENT.json',{'initial_frozen_digest':frozen,
    'failure':'Both initial final runs stopped at evaluation/background/11 teacher; existing S1 receiver abstained. Harness incorrectly asserted every reception must succeed.',
    'planned_change':'Record held input and skip its teacher transaction unchanged, for all paired modes. Derive saved-memory counts from actually learned documents.',
    'unchanged':'SS core, corpus, codes, thresholds, random seeds, modes, test cases, protocol and acceptance rules are unchanged.',
    'acceptance_intent':'The original all-input-meaning-equal check remains strict; a held input makes that check fail. Do not hide this by removing the case or retrying another seed.',
    'initial_completed_results':0,'eligible_for_inference':False})
print({'archived_initial_freeze':frozen})
