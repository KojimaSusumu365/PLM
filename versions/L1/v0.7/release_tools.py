"""Additive freeze, old-release checks, demonstrations and immutable packaging."""
import argparse
import hashlib
import json
import zipfile
from evaluate import ROOT,source_files,verify_freeze
from evaluation_support import V06
from plm_l1_v06.algebra import digest
from plm_l1_v07.runtime import EventModel


def hashes(files,root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=("freeze","check-baseline","demo","pack"))
    command=parser.parse_args().command
    if command=="freeze":
        manifest={"schema":"plm-l1-v07-source-freeze-v1","files":hashes(source_files(),ROOT)}
        write(ROOT/"SOURCE_MANIFEST.json",manifest)
        print(json.dumps({"files":len(manifest["files"]),"digest":digest(manifest)}))
    elif command=="check-baseline":
        baseline=json.loads((ROOT/"verification"/"PRESERVED_BASELINE.json").read_text(encoding="utf-8"))
        files=[]
        for name in ("PLM-L1-v0.1","PLM-L1-v0.2","PLM-L1-v0.3","PLM-L1-v0.4","PLM-L1-v0.5","PLM-L1-v0.6","PLM-P1-v0.2","PLM-S1-v0.2"):
            files.extend(p for p in (ROOT.parent/name).rglob("*") if p.is_file())
            files.append(ROOT.parent/(name+".zip"))
        if hashes(files,ROOT.parent)!=baseline:
            raise ValueError("old release changed")
        old=ROOT.parent/"PLM-L1-v0.6"
        if hashes([p for p in old.rglob("*") if p.is_file()],old)!=hashes([p for p in V06.rglob("*") if p.is_file()],V06):
            raise ValueError("vendored v0.6 changed")
        print(json.dumps({"status":"unchanged","preserved_files":len(baseline),"vendor_files":len([p for p in V06.rglob("*") if p.is_file()])}))
    elif command=="demo":
        m=EventModel.load(ROOT/"results"/"model")
        texts=("太郎が花子を助けた。花子が太郎を助けなかった。","もし太郎が花子を助けたら。花子が健太を褒めなかった。",
               "太郎が花子を助けた。太郎が花子を助けた。","太郎が花子を助けた。彼が太郎を助けた。")
        rows=[]
        for index,text in enumerate(texts):
            r=m.read(text); row={"input":text,"status":r["status"],"reason":r.get("reason")}
            if r["status"]=="read":
                row["meaning"]=m.recover(r["packet"])["meaning"]
                row["generated"]=m.generate(r["packet"],["object","subject"])
                if index==0:
                    write(ROOT/"examples"/"MEANING.json",row["meaning"])
                    write(ROOT/"examples"/"MEANING_PACKET.json",r["packet"])
            rows.append(row)
        write(ROOT/"examples"/"ROUNDTRIPS.json",{"scope":"Human/evaluator only; original text is not generator input","demos":rows})
    else:
        verify_freeze()
        v=json.loads((ROOT/"verification"/"REPRODUCIBILITY.json").read_text(encoding="utf-8"))
        if v["status"]!="passed" or v["complete_numeric_runs"]!=2:
            raise ValueError("completed reproducibility verification required")
        archive=ROOT.parent/"PLM-L1-v0.7.zip"; checksum=ROOT.parent/"PLM-L1-v0.7.sha256"
        if archive.exists() or checksum.exists():
            raise ValueError("archive already exists")
        files=sorted(p for p in ROOT.rglob("*") if p.is_file() and p!=ROOT/"RELEASE_MANIFEST.json" and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0]!="work")
        write(ROOT/"RELEASE_MANIFEST.json",{"schema":"plm-l1-v07-release-v1","files":hashes(files,ROOT)})
        with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED,compresslevel=9) as stream:
            for path in files+[ROOT/"RELEASE_MANIFEST.json"]:
                stream.write(path,ROOT.name+"/"+path.relative_to(ROOT).as_posix())
        sha=hashlib.sha256(archive.read_bytes()).hexdigest()
        with checksum.open("x",encoding="utf-8") as stream:
            stream.write(sha+"  "+archive.name+"\n")
        print(json.dumps({"archive":str(archive),"bytes":archive.stat().st_size,"files":len(files)+1,"sha256":sha}))


if __name__=="__main__":
    main()
