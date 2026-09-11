"""Freeze sources, framing, protocol, examples, vendor and development evidence."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/"SOURCE_MANIFEST.json"


def snapshot():
    files=list(ROOT.glob("*.py"))+list(ROOT.glob("*.md"))+[ROOT/"requirements.txt",ROOT/"WIRE_CONTRACT.json"]
    for name in ("plm_s1_v02","tests","evaluation","vendor","examples"):
        files.extend((ROOT/name).rglob("*"))
    files.extend(ROOT/"results"/name for name in ("DEVELOPMENT_RESULTS.json","DEVELOPMENT_REPORT.md"))
    return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(set(files)) if p.is_file() and "__pycache__" not in p.parts and p.suffix!=".pyc"}


def verify():
    if not MANIFEST.exists(): return {"valid":False,"differences":["missing source manifest"],"verified_files":0}
    expected=json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    actual=snapshot()
    differences=sorted(k for k in expected.keys()|actual.keys() if expected.get(k)!=actual.get(k))
    return {"valid":not differences,"differences":differences,"verified_files":len(actual)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--create",action="store_true")
    args=parser.parse_args()
    if args.create:
        if (ROOT/"EVALUATION_STARTED.json").exists() or (ROOT/"FIRST_EVALUATION.json").exists(): raise SystemExit("Refuse source freeze after evaluation began")
        with MANIFEST.open("x",encoding="utf-8") as f:
            json.dump({"version":"PLM-S1 v0.2","frozen_at_utc":datetime.now(timezone.utc).isoformat(),"files":snapshot()},f,indent=2)
            f.write("\n")
    result=verify()
    print(json.dumps(result))
    if not result["valid"]: raise SystemExit(1)


if __name__=="__main__": main()


