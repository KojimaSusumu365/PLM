"""Evaluator-only independent grammar and old regression interfaces."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
V06=ROOT/"vendor"/"PLM-L1-v0.6"
V05=V06/"vendor"/"PLM-L1-v0.5"
V04=V05/"vendor"/"PLM-L1-v0.4"
V03=V04/"vendor"/"PLM-L1-v0.3"
V02=V03/"vendor"/"PLM-L1-v0.2"
V01=V02/"vendor"/"PLM-L1-v0.1"
for path in (V06,V05,V04,V03,V02,V01):
    if str(path) not in sys.path:
        sys.path.append(str(path))
spec=importlib.util.spec_from_file_location("event_legacy_support",V06/"evaluation_support.py")
legacy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
interpret,text_goal,heldout=legacy.interpret,legacy.text_goal,legacy.heldout
from plm_l1.teacher import surface,VERBS

GOAL_PAIRS=[[a,b] for a in ("subject","object") for b in ("subject","object")]
CATEGORIES=("separate_participants","shared_subject","shared_object","role_chain","role_reversal","polarity_scope","modality_scope","identical_mentions","predicate_scope")


def data(name):
    return json.loads((ROOT/"data"/(name+".json")).read_text(encoding="utf-8"))


def render(event,goal):
    stem=dict(("predicate:"+pred,stem) for stem,pred in VERBS)[event["predicate"]]
    return surface(event["subject"].split(":",1)[1],event["object"].split(":",1)[1],stem,event["polarity"].split(":",1)[1],event["modality"].split(":",1)[1],goal+"_first")


def parse_document(text):
    if type(text) is not str or text.count("。")!=2 or not text.endswith("。"):
        return None
    events=[interpret(part+"。") for part in text.split("。")[:2]]
    return {"events":events} if all(e is not None for e in events) else None


def document_goals(text):
    return [text_goal(part+"。") for part in text.split("。")[:2]] if parse_document(text) is not None else None
