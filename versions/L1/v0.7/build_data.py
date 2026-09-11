"""Compose new two-event data with an evaluator-only synthetic grammar."""
import hashlib
import json
from plm_l1_v06.algebra import canonical
from evaluation_support import ROOT,data,render,CATEGORIES,GOAL_PAIRS,parse_document


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def build(split):
    lex=data("lexicon")
    names=lex["slot_candidates"]["subject"]
    predicates=lex["slot_candidates"]["predicate"]
    triples=sorted({tuple(r["meaning"][k] for k in ("subject","object","predicate")) for r in data(split)},key=lambda t:hashlib.sha256(canonical(["event-corpus-v1",t]).encode()).hexdigest())[:8]
    rows=[]
    for index,(subject,obj,predicate) in enumerate(triples):
        first={"subject":subject,"object":obj,"predicate":predicate,"polarity":"polarity:"+("negative" if index%2 else "positive"),"modality":"modality:"+("hypothetical" if (index//2)%2 else "asserted")}
        others=[n for n in names if n not in (subject,obj)]
        alternate=predicates[(predicates.index(predicate)+1)%len(predicates)]
        variants={
            "separate_participants":dict(first,subject=others[0],object=others[1],predicate=alternate),
            "shared_subject":dict(first,object=others[0],predicate=alternate),
            "shared_object":dict(first,subject=others[0],predicate=alternate),
            "role_chain":dict(first,subject=obj,object=others[0],predicate=alternate),
            "role_reversal":dict(first,subject=obj,object=subject),
            "polarity_scope":dict(first,polarity="polarity:positive" if index%2 else "polarity:negative"),
            "modality_scope":dict(first,modality="modality:asserted" if (index//2)%2 else "modality:hypothetical"),
            "identical_mentions":dict(first),
            "predicate_scope":dict(first,predicate=alternate),
        }
        for category in CATEGORIES:
            meaning={"events":[first,variants[category]]}
            for goal_index,goals in enumerate(GOAL_PAIRS):
                text=render(first,goals[0])+render(variants[category],goals[1])
                assert parse_document(text)==meaning
                rows.append({"id":f"{split}-{index}-{category}-{goal_index}","category":category,"text":text,"meaning":meaning,"input_goals":goals})
    assert len(rows)==288 and len({r["text"] for r in rows})==288
    return rows


def main():
    development,evaluation=build("development"),build("evaluation")
    a={canonical(r["meaning"]) for r in development}
    b={canonical(r["meaning"]) for r in evaluation}
    assert not a&b
    write(ROOT/"data"/"events_development.json",development)
    write(ROOT/"data"/"events_evaluation.json",evaluation)
    train=data("folds/object_negative/train")
    train_triples={tuple(r["meaning"][k] for k in ("subject","object","predicate")) for r in train}
    audit={"schema":"plm-two-event-corpus-audit-v1","component_training_pairs":len(train),"two_event_training_pairs":0,
           "development_documents":len(development),"evaluation_documents":len(evaluation),"development_meanings":len(a),"evaluation_meanings":len(b),
           "ordered_pair_overlap":len(a&b),"categories":list(CATEGORIES),"input_goal_pairs":GOAL_PAIRS,
           "evaluation_first_event_lexical_triple_absent_from_training":all(tuple(r["meaning"]["events"][0][k] for k in ("subject","object","predicate")) not in train_triples for r in evaluation),
           "scope":"New ordered pairs and new paired texts, built from old controlled grammar/vocabulary and reused one-event split. Not an independently collected natural-language corpus. Sentence segmentation/event positions designed, not learned."}
    write(ROOT/"data"/"EVENT_SPLIT_AUDIT.json",audit)
    print(json.dumps(audit,ensure_ascii=False))


if __name__=="__main__":
    main()
