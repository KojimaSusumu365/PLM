import hashlib
import json
from pathlib import Path

outputs=Path(__file__).resolve().parent.parent/"outputs"
names=("PLM-L1-v0.1","PLM-L1-v0.2","PLM-L1-v0.3","PLM-L1-v0.4","PLM-L1-v0.5","PLM-L1-v0.6","PLM-P1-v0.2","PLM-S1-v0.2")
files=[]
for name in names:
    files.extend(p for p in (outputs/name).rglob("*") if p.is_file())
    files.append(outputs/(name+".zip"))
record={p.relative_to(outputs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
with (outputs/"PLM-L1-v0.7"/"verification"/"PRESERVED_BASELINE.json").open("x",encoding="utf-8") as stream:
    stream.write(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"preserved_files":len(record)}))
