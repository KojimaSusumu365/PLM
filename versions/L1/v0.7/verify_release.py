"""Test all versions, verify result integrity, isolate training and generation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from evaluate import verify_freeze,judge
from evaluation_support import ROOT,V06,V05,V04,V03,V02,V01,data,parse_document,document_goals
from plm_l1_v06.algebra import digest
from plm_l1_v07.runtime import EventModel,PACKET_FIELDS


def run(arguments,cwd,output,label,expected=0):
    env=dict(os.environ,OPENBLAS_NUM_THREADS="1",PYTHONIOENCODING="utf-8",PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
    env.pop("PYTHONPATH",None)
    result=subprocess.run([sys.executable,"-B",*arguments],cwd=cwd,env=env,capture_output=True,text=True,encoding="utf-8",timeout=240)
    log=result.stdout+result.stderr
    (output/(label+".log")).write_text(log,encoding="utf-8")
    if result.returncode!=expected:
        raise ValueError(label+" failed: "+log[-3000:])
    return result.stdout,log


def copy_package(source,target,excluded=()):
    target.mkdir(parents=True)
    for path in sorted(source.glob("*.py")):
        if path.name not in excluded:
            shutil.copyfile(path,target/path.name)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--preflight",action="store_true")
    args=parser.parse_args()
    output=Path(args.out).resolve()
    if output.exists():
        raise ValueError("fresh verification directory required")
    output.mkdir(parents=True)
    p=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
    if args.preflight:
        from plm_l1_v07.training import fit
        model=fit(data("folds/"+p["component_fold"]+"/train"),data("lexicon"),component_seed=p["component_seed"],event_seed=p["development_seeds"][0])
        freeze,claimed,checks="preflight_not_frozen",None,[]
    else:
        freeze=verify_freeze()
        r=json.loads((ROOT/"results"/"EVALUATION.json").read_text(encoding="utf-8"))
        claimed=r.pop("result_digest")
        if digest(r)!=claimed or r["freeze_hash"]!=freeze:
            raise ValueError("evaluation integrity failure")
        checks=judge(r,p)
        if checks!=r["checks"] or not all(c["passed"] for c in checks):
            raise ValueError("acceptance failure")
        model=EventModel.load(ROOT/"results"/"model")
        if model.fingerprint!=r["standard"][0]["fingerprint"] or model.component.fingerprint!=r["component_fingerprint"]:
            raise ValueError("saved model differs from evaluation")
    test_counts={}
    for label,cwd in (("NEW_TESTS",ROOT),("V06_TESTS",V06),("V05_TESTS",V05),("V04_TESTS",V04),("V03_TESTS",V03),("V02_TESTS",V02),("V01_TESTS",V01)):
        _,log=run(["-m","unittest","discover","-s","tests","-v"],cwd,output,label)
        test_counts[label]=int(re.search(r"Ran (\d+) tests",log).group(1))
    training=output/"pair-training-only"
    for name in ("plm_l1_v07","plm_l1_v06"):
        copy_package(ROOT/name,training/name)
    shutil.copyfile(ROOT/"data"/"folds"/p["component_fold"]/"train.json",training/"train.json")
    shutil.copyfile(ROOT/"data"/"lexicon.json",training/"lexicon.json")
    assertion="from pathlib import Path; import importlib.util; assert not Path('vendor').exists(); assert not Path('events_evaluation.json').exists(); assert all(importlib.util.find_spec(n) is None for n in ('evaluation_support','plm_l1_v05','plm_l1')); print('only current component package and single-event training pairs; no two-event corpus or legacy teacher')"
    run(["-c",assertion],training,output,"PAIR_TRAIN_BOUNDARY")
    stdout,_=run(["-m","plm_l1_v07","train","--pairs","train.json","--lexicon","lexicon.json","--component-seed",model.component.meta["seed"],"--event-seed",model.meta["seed"],"--dimension",str(model.meta["dimension"]),"--mode",model.meta["mode"],"--out","model"],training,output,"PAIR_TRAIN")
    if json.loads(stdout)["fingerprint"]!=model.fingerprint:
        raise ValueError("isolated learning differs")
    generation=output/"generation-only"
    for name in ("plm_l1_v07","plm_l1_v06"):
        copy_package(ROOT/name,generation/name,{"reader.py","training.py"})
    shutil.copytree(training/"model",generation/"model")
    assertion="from pathlib import Path; import importlib.util; assert all(importlib.util.find_spec(n) is None for n in ('plm_l1_v07.reader','plm_l1_v07.training','plm_l1_v06.reader','plm_l1_v06.training','evaluation_support','plm_l1_v05','plm_l1')); assert not Path('train.json').exists(); print('no reader or training entrypoints, original texts, event corpus, or legacy teacher; shared weights/helpers remain')"
    run(["-c",assertion],generation,output,"GENERATION_BOUNDARY")
    texts=("太郎が花子を助けた。花子が太郎を助けなかった。","もし太郎が花子を助けたら。花子が健太を褒めなかった。",
           "太郎が花子を助けた。太郎が美咲を訪ねた。","太郎が花子を助けた。太郎が花子を助けた。")
    demos=[]
    for index,text in enumerate(texts):
        name=f"packet-{index}.json"
        run(["-m","plm_l1_v07","read","--model","model","--text",text,"--out",name],training,output,f"READ_{index}")
        packet=json.loads((training/name).read_text(encoding="utf-8"))
        if set(packet)!=PACKET_FIELDS or any(type(x) not in (float,int) for k in ("real","imag") for x in packet[k]):
            raise ValueError("non-numerical transfer")
        shutil.copyfile(training/name,generation/name)
        stdout,_=run(["-m","plm_l1_v07","generate","--model","model","--packet",name,"--goals","object","subject"],generation,output,f"GENERATE_{index}")
        out=json.loads(stdout)
        if out["status"]!="generated" or parse_document(out["text"])!=parse_document(text) or document_goals(out["text"])!=["object","subject"]:
            raise ValueError("isolated event generation failed")
        demos.append({"input_for_verifier_only":text,"output":out["text"],"both_events_meaning_and_goals_exact":True})
    assertion="import json; from unittest.mock import patch; from plm_l1_v07.runtime import EventModel; m=EventModel.load('model'); p=json.load(open('packet-0.json',encoding='utf-8')); guard=patch('plm_l1_v06.banked.dependency_leaves',side_effect=AssertionError('runtime retraining')); guard.start(); assert m.generate(p)['status']=='generated'; print('no runtime feature learning')"
    run(["-c",assertion],generation,output,"NO_RUNTIME_FEATURE_LEARNING")
    run(["-m","plm_l1_v07","read","--model","model","--text","太郎が花子を助けた。彼が太郎を助けた。","--out","must-not-exist.json"],training,output,"ATOMIC_ABSTAIN",expected=2)
    if (training/"must-not-exist.json").exists():
        raise ValueError("partial document packet emitted")
    manifest_path=ROOT/"RELEASE_MANIFEST.json"
    manifest_checked=False
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob("*") if p.is_file() and p!=manifest_path and "__pycache__" not in p.parts and p.relative_to(ROOT).parts[0]!="work"}
        if actual!=manifest["files"]:
            raise ValueError("release file inventory or bytes changed")
        manifest_checked=True
    report={"status":"passed","preflight":args.preflight,"source_freeze":freeze,"result_digest":claimed,"acceptance_checks":len(checks),"test_counts":test_counts,
            "single_event_pair_training_only":True,"two_event_training_examples":0,"isolated_model_fingerprint_equal":True,"model_fingerprint":model.fingerprint,
            "component_fingerprint":model.component.fingerprint,"generation_without_both_reader_and_training_entrypoints":True,"single_numerical_packet_only_transfer":True,
            "atomic_abstention_without_partial_packet":True,"no_runtime_feature_learning":True,"isolated_roundtrips":demos,
            "boundary_limit":"Shared learned v0.6 component weights and helpers remain; two-event boundaries/bindings are designed, not learned.",
            "release_manifest_checked":manifest_checked,"full_numeric_rerun_in_this_command":False,"python":sys.version}
    (output/"VERIFICATION.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
