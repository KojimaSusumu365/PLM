"""Blind task preparation and fixed, span-based independent-evaluation scaffolding."""
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
from .contract import canonical, content_id, digest, require
from .producer import analyze, export_observations, VENDOR

PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "PROTOCOL.json"
PROTOCOL = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
TYPES = {"FINANCIAL_AFFORDANCE", "SPATIAL_ASSOCIATION", "COREFERENCE", "REVISION"}
SLOTS = ("relation_type", "anchor", "subject", "predicate", "object", "target", "voice", "polarity", "modality")


def prior_exposure_texts():
    """Conservative exact-text blacklist; near-duplicates still require human audit."""
    texts = set()
    def walk(value):
        if isinstance(value, str):
            texts.add(value.strip())
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
    for path in (VENDOR / "data").glob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    demo_path = PROTOCOL_PATH.parent / "integration_cases.json"
    if demo_path.exists():
        walk(json.loads(demo_path.read_text(encoding="utf-8")))
    return texts


def prepare(corpus, *, dataset_kind="real_world"):
    require(dataset_kind in {"real_world", "synthetic"}, "Invalid dataset kind")
    require(type(corpus) is list, "Corpus must be list")
    items, contents, sources, source_texts = [], set(), set(), set()
    exposed = prior_exposure_texts() if dataset_kind == "real_world" else set()
    for index, row in enumerate(corpus):
        require(type(row) is dict, "Invalid corpus row")
        inputs = row.get("inputs")
        require(type(inputs) is list and inputs and all(type(t) is str and t.strip() for t in inputs), "Nonempty raw inputs required")
        require(type(row.get("source_id")) is str and row["source_id"].strip(), "Source ID required")
        require(type(row.get("revision")) is str and row["revision"].strip(), "Revision required")
        require(type(row.get("source_group")) is str and row["source_group"].strip(), "Source group required")
        require(row.get("stratum") in PROTOCOL["strata"], "Unknown sampling stratum")
        require(type(row.get("provenance")) is str and row["provenance"].strip(), "Source provenance required")
        doc = content_id(inputs)
        source = (row["source_id"], row["revision"])
        require(doc not in contents and source not in sources, "Duplicate evaluation document/source")
        normalized = {t.strip() for t in inputs}
        require(not normalized & source_texts, "Repeated source text across evaluation documents")
        require(not normalized & exposed, "Previously exposed text is not independent evaluation material")
        contents.add(doc)
        sources.add(source)
        source_texts.update(normalized)
        items.append({"task_id": f"R1P-{index + 1:03d}", "source_id": row["source_id"],
                      "revision": row["revision"], "source_group": row["source_group"],
                      "stratum": row["stratum"], "provenance": row["provenance"],
                      "inputs": deepcopy(inputs), "document_id": doc, "status": "pending",
                      "annotations": [], "adjudication": None, "exclusion_reason": None})
    return {"protocol_version": PROTOCOL["protocol_version"], "protocol_hash": digest(PROTOCOL),
            "dataset_kind": dataset_kind,
            "process_declaration": {"independent_of_implementation": False, "blind_to_predictions": False,
                                    "near_duplicate_audit_complete": False, "statement": None},
            "items": items}


def task_manifest(batch):
    fields = ("task_id", "source_id", "revision", "source_group", "stratum", "provenance", "inputs", "document_id")
    frozen = [{key: item[key] for key in fields} for item in batch["items"]]
    return {"protocol_hash": batch["protocol_hash"], "dataset_kind": batch["dataset_kind"],
            "document_count": len(frozen), "task_content_hash": digest(frozen)}


def _validate_span(span, inputs, *, nullable=False):
    if nullable and span is None:
        return
    require(type(span) is dict and set(span) == {"source_index", "start", "end"}, "Invalid annotation span")
    i, start, end = span["source_index"], span["start"], span["end"]
    require(all(type(x) is int for x in (i, start, end)), "Span offsets must be integers")
    require(0 <= i < len(inputs) and 0 <= start < end <= len(inputs[i]), "Annotation span out of range")


def validate_relations(relations, inputs):
    require(type(relations) is list, "Relations must be a list, not null")
    seen = set()
    for relation in relations:
        require(type(relation) is dict and set(relation) == set(SLOTS), "Invalid relation fields")
        require(relation["relation_type"] in TYPES, "Unknown relation type")
        require(type(relation["predicate"]) is str and relation["predicate"].strip(), "Predicate required")
        require(relation["voice"] in {"active", "passive", "n/a"}, "Invalid voice")
        require(relation["polarity"] in {"positive", "negative"}, "Invalid polarity")
        require(relation["modality"] in {"asserted", "hypothetical", "corrective", "provisional", "retracted", "quoted"}, "Invalid modality")
        _validate_span(relation["anchor"], inputs)
        for field in ("subject", "object", "target"):
            _validate_span(relation[field], inputs, nullable=True)
        if relation["relation_type"] == "REVISION":
            require(relation["subject"] is None and relation["object"] is None and relation["target"] is not None
                    and relation["predicate"] == "REVISES", "Invalid revision annotation")
        else:
            require(relation["subject"] is not None and relation["object"] is not None and relation["target"] is None, "Role spans required")
        if relation["relation_type"] == "COREFERENCE":
            require(relation["predicate"] == "REFERS_TO", "Invalid coreference predicate")
        if relation["relation_type"] == "SPATIAL_ASSOCIATION":
            require(relation["predicate"] == "LOCATED_NEAR", "Invalid spatial predicate")
        key = canonical(relation)
        require(key not in seen, "Duplicate gold relation")
        seen.add(key)


def prediction_relations(analysis, *, checked_only=True):
    """Map clause-local producer offsets to raw-source Unicode codepoint offsets.

    A failed mapping is returned as an unmatched prediction, never silently dropped.
    """
    env = export_observations(analysis)
    inputs = analysis["inputs"]
    clauses, cursor = {}, defaultdict(int)
    for clause in env["clauses"]:
        i, text = clause["source_order"], clause["text"]
        pos = inputs[i].find(text, cursor[i])
        if pos < 0:
            clauses[clause["clause_id"]] = None
        else:
            clauses[clause["clause_id"]] = {"source_index": i, "start": pos, "end": pos + len(text)}
            cursor[i] = pos + len(text)
    mentions = {m["mention_id"]: m for m in env["mentions"]}
    def local(clause_id, span=None):
        base = clauses.get(clause_id)
        require(base is not None, "Unmappable clause")
        if span is None:
            return deepcopy(base)
        return {"source_index": base["source_index"], "start": base["start"] + span["start"], "end": base["start"] + span["end"]}
    def role(mid):
        if mid is None:
            return None
        mention = mentions[mid]
        return local(mention["clause_id"], mention["span"])
    predictions, unmappable = [], []
    for frame in env["observations"]:
        if checked_only and frame["semantic_status"] != "rule_checked":
            continue
        try:
            subject, obj = role(frame["subject_mention_id"]), role(frame["object_mention_id"])
            kind = frame["relation_type"]
            anchor = subject if kind == "COREFERENCE" else local(frame["clause_id"], frame["predicate_span"])
            row = {"relation_type": kind, "anchor": anchor, "subject": subject, "object": obj,
                   "predicate": frame["predicate"], "target": local(frame["target_clause_id"]) if kind == "REVISION" else None,
                   "voice": frame["voice"], "polarity": frame["polarity"], "modality": frame["modality"]}
            validate_relations([row], inputs)
            predictions.append(row)
        except (KeyError, ValueError) as error:
            unmappable.append({"observation_id": frame["observation_id"], "reason": str(error)})
    return predictions, unmappable


def relation_metrics(predictions, gold, *, unmappable_count=0):
    p, g = Counter(map(canonical, predictions)), Counter(map(canonical, gold))
    tp = sum((p & g).values())
    fp, fn = sum(p.values()) + unmappable_count - tp, sum(g.values()) - tp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def slot_metrics(predictions, gold):
    # Avoid arbitrary pairing in plural/many-to-many cases. Exact multiset score still covers them.
    def grouped(rows):
        groups = defaultdict(list)
        for row in rows:
            groups[(row["relation_type"], canonical(row["anchor"]))].append(row)
        return groups
    pg, gg = grouped(predictions), grouped(gold)
    slots = {key: {"correct": 0, "aligned": 0} for key in SLOTS if key not in {"anchor", "relation_type"}}
    for key in pg.keys() & gg.keys():
        if len(pg[key]) == len(gg[key]) == 1:
            for slot in slots:
                slots[slot]["aligned"] += 1
                slots[slot]["correct"] += pg[key][0][slot] == gg[key][0][slot]
    return slots


def evaluate(batch, manifest=None):
    require(batch.get("protocol_version") == PROTOCOL["protocol_version"] and batch.get("protocol_hash") == digest(PROTOCOL), "Protocol freeze mismatch")
    require(batch.get("dataset_kind") in {"real_world", "synthetic"}, "Invalid dataset kind")
    items = batch.get("items")
    require(type(items) is list, "items required")
    if manifest is not None:
        require(manifest == task_manifest(batch), "Frozen task manifest mismatch")
    # Recheck identity, contamination and source fields after editable annotation roundtrip.
    prepared = prepare(items, dataset_kind=batch["dataset_kind"])
    require(len({r.get("task_id") for r in items}) == len(items), "Duplicate task ID")
    pending, exclusions, completed = [], [], []
    for item, expected in zip(items, prepared["items"]):
        require(type(item.get("task_id")) is str and item["task_id"], "Task ID required")
        require(item.get("document_id") == expected["document_id"], "Annotation content hash mismatch")
        require(item.get("status") in {"pending", "adjudicated", "excluded"}, "Invalid task status")
        if item["status"] == "pending":
            pending.append(item["task_id"])
            continue
        if item["status"] == "excluded":
            require(type(item.get("exclusion_reason")) is str and item["exclusion_reason"].strip(), "Exclusion reason required")
            exclusions.append({"task_id": item["task_id"], "reason": item["exclusion_reason"]})
            continue
        annotations = item.get("annotations")
        require(type(annotations) is list and len(annotations) >= 2, "Two independent annotations required")
        annotators = [a.get("annotator_id") for a in annotations]
        require(all(type(a) is str and a.strip() for a in annotators) and len(set(annotators)) == len(annotators), "Distinct annotator IDs required")
        for annotation in annotations:
            validate_relations(annotation.get("relations"), item["inputs"])
        adjudication = item.get("adjudication")
        require(type(adjudication) is dict and type(adjudication.get("adjudicator_id")) is str and adjudication["adjudicator_id"].strip(), "Adjudicator required")
        require(adjudication["adjudicator_id"] not in annotators, "Adjudicator must be separate from annotators")
        require(type(adjudication.get("rationale")) is str and adjudication["rationale"].strip(), "Adjudication rationale required")
        validate_relations(adjudication.get("relations"), item["inputs"])
        completed.append(item)
    declaration = batch.get("process_declaration", {})
    barriers = []
    if not items:
        barriers.append("real_corpus_not_supplied")
    if pending:
        barriers.append("annotations_pending")
    if not completed:
        barriers.append("no_adjudicated_gold")
    if batch["dataset_kind"] == "real_world":
        if manifest is None:
            barriers.append("missing_frozen_task_manifest")
        if len(completed) < PROTOCOL["minimum_adjudicated_documents"]:
            barriers.append("fewer_than_50_adjudicated_documents")
        for key in ("independent_of_implementation", "blind_to_predictions", "near_duplicate_audit_complete"):
            if declaration.get(key) is not True:
                barriers.append("missing_declaration:" + key)
        if not isinstance(declaration.get("statement"), str) or not declaration["statement"].strip():
            barriers.append("missing_process_statement")
    report = {"protocol_version": PROTOCOL["protocol_version"], "protocol_hash": digest(PROTOCOL),
              "dataset_kind": batch["dataset_kind"], "total_documents": len(items),
              "adjudicated_documents": len(completed), "pending_task_ids": pending,
              "exclusions": exclusions, "barriers": barriers,
              "independence": "not_externally_verified_declaration_only", "inference_enabled": False,
              "task_manifest_verified": manifest is not None,
              "sampling_counts": dict(Counter(i["stratum"] for i in items)),
              "source_group_count": len({i["source_group"] for i in items}),
              "sampling_shortfalls": {s: max(0, n - sum(i["stratum"] == s for i in completed)) for s, n in PROTOCOL["strata"].items()},
              "metrics": None, "status": "pending_inputs" if barriers else "ready_to_score"}
    if barriers:
        return report
    all_predictions, all_gold, all_raw, unmapped, raw_unmapped, rows = [], [], [], 0, 0, []
    slots = {key: {"correct": 0, "aligned": 0} for key in SLOTS if key not in {"anchor", "relation_type"}}
    agreement_count = 0
    for item in completed:
        analysis = analyze(item["inputs"])
        preds, bad = prediction_relations(analysis)
        raw, raw_bad = prediction_relations(analysis, checked_only=False)
        gold = item["adjudication"]["relations"]
        all_predictions.extend(preds)
        all_gold.extend(gold)
        all_raw.extend(raw)
        unmapped += len(bad)
        raw_unmapped += len(raw_bad)
        metrics = relation_metrics(preds, gold, unmappable_count=len(bad))
        raw_metrics = relation_metrics(raw, gold, unmappable_count=len(raw_bad))
        for key, value in slot_metrics(preds, gold).items():
            for field in value:
                slots[key][field] += value[field]
        first_two = item["annotations"][:2]
        agreed = Counter(map(canonical, first_two[0]["relations"])) == Counter(map(canonical, first_two[1]["relations"]))
        agreement_count += agreed
        rows.append({"task_id": item["task_id"], "stratum": item["stratum"], "metrics": metrics,
                     "raw_metrics": raw_metrics, "unmappable_predictions": bad,
                     "first_two_annotators_exact_agreement": agreed,
                     "document_exact": metrics["fp"] == 0 and metrics["fn"] == 0})
    # Sum per-document counts; never match identical offsets across separate documents.
    def total(field, selected):
        tp, fp, fn = (sum(r[field][k] for r in selected) for k in ("tp", "fp", "fn"))
        return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}
    report.update(status="scored_synthetic_only" if batch["dataset_kind"] == "synthetic" else "scored_declared_independent_pilot",
                  metrics=total("metrics", rows), raw_candidate_metrics=total("raw_metrics", rows),
                  by_stratum={s: {"documents": sum(r["stratum"] == s for r in rows),
                                 "metrics": total("metrics", [r for r in rows if r["stratum"] == s])}
                              for s in PROTOCOL["strata"]},
                  slot_metrics_unique_anchor_alignment_only=slots,
                  first_two_annotators_exact_document_agreement=agreement_count / len(rows),
                  document_exact_count=sum(r["document_exact"] for r in rows),
                  unmappable_prediction_count=unmapped, raw_unmappable_prediction_count=raw_unmapped, rows=rows)
    return report
