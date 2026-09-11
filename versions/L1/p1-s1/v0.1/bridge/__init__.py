"""L1 numeric meaning -> P1 phase carrier -> frozen S1 chips -> L1 operations."""
from pathlib import Path
import sys
VENDOR=Path(__file__).resolve().parents[1]/'vendor/PLM-S1-v0.2'
if str(VENDOR) not in sys.path:sys.path.append(str(VENDOR))
import plm_s1_v02
VERSION='PLM-L1-P1-S1 v0.1'
