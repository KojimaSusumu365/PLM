"""Mechanical namespace/constant migration of copied v0.8 code only."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] / 'outputs' / 'PLM-L1-v0.9' / 'plm_l1_v09'
assert ROOT.is_dir() and ROOT.name == 'plm_l1_v09'
names = ['contract.py', 'codec.py', 'runtime.py', 'training.py', 'reader.py']
for name in names:
    p = ROOT / name
    s = p.read_text(encoding='utf-8').replace('from plm_l1_v06.', 'from .component.')
    s = s.replace('plm-temporal-model-v1', 'plm-temporal-model-v09').replace('plm-temporal-signal-v1', 'plm-temporal-signal-v09')
    p.write_text(s, encoding='utf-8')
for name in ('runtime.py', 'training.py'):
    p = ROOT / 'component' / name
    s = p.read_text(encoding='utf-8').replace('plm-l1-banked-v1', 'plm-l1-component-v09')
    s = s.replace('plm-l1-banked-meaning-v1', 'plm-l1-component-meaning-v09')
    p.write_text(s, encoding='utf-8')
for relative in ('codec.py', 'component/runtime.py', 'component/banked.py', 'component/projection.py', 'component/algebra.py'):
    p = ROOT / relative
    s = p.read_text(encoding='utf-8')
    constants = 'from ' + ('..' if '/' in relative else '.') + 'thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MIN_PROOF, MAX_RESIDUAL, LEGACY_MIN_SCORE\n'
    s = s.replace('import numpy as np', 'import numpy as np\n' + constants)
    s = s.replace('top>=.65', 'top>=MIN_SCORE').replace('top >= .65', 'top >= MIN_SCORE')
    s = s.replace('margin>=.25', 'margin>=MIN_MARGIN').replace('top-runner>=.25', 'top-runner>=MIN_MARGIN')
    s = s.replace('top-runner >= .25', 'top-runner >= MIN_MARGIN').replace('top - runner >= .25', 'top - runner >= MIN_MARGIN')
    s = s.replace('strength>=.65', 'strength>=MIN_PRESENCE').replace('evidence>=.65', 'evidence>=MIN_PROOF')
    s = s.replace('residual<=.20', 'residual<=MAX_RESIDUAL').replace('residual <= .20', 'residual <= MAX_RESIDUAL')
    s = s.replace('minimum=0.60, margin=0.25', 'minimum=LEGACY_MIN_SCORE, margin=MIN_MARGIN')
    p.write_text(s, encoding='utf-8')
print('mechanical import, schema and threshold migration complete')
