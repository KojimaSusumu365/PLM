"""Fixed v0.2 reader integration. Imported only by callers that request it."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "PLM-L1-v0.2"


def fixed_reader():
    if str(VENDOR) not in sys.path:
        sys.path.insert(1, str(VENDOR))
    from plm_l1_v02.runtime import PairReader
    return PairReader.load(VENDOR / "results" / "reader")


def translate(reader, packet, writer):
    recovered = reader.recover(packet)
    if recovered["status"] != "recovered":
        return {"status": "abstain", "reason": recovered["reason"], "packet": None}
    try:
        return {"status": "bridged", "packet": writer.encode(recovered["slots"]), "eligible_for_inference": False}
    except ValueError as error:
        return {"status": "abstain", "reason": str(error), "packet": None}
