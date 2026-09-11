"""Independent contract checks and a fail-closed observation-only export.

Runtime checks are rule consistency checks, not a gold-standard semantic score.
The evaluator compares outputs against separately annotated expectations.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import re
from .semantics import bank_event, SPATIAL_RE

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "RELATION_SCHEMA.json").read_text(encoding="utf-8"))


def validate_schema(value, schema=SCHEMA, path="frame"):
    """Validate exactly the JSON Schema keywords used by the bundled schema."""
    errors = []
    kind = "null" if value is None else "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "number" if isinstance(value, float) else "string" if isinstance(value, str) else "array" if isinstance(value, list) else "object" if isinstance(value, dict) else "invalid"
    expected = schema.get("type", [])
    expected = [expected] if isinstance(expected, str) else expected
    if expected and kind not in expected:
        return [f"{path}:type"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}:enum")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{path}:pattern")
    if kind in {"integer", "number"} and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}:minimum")
    if isinstance(value, dict):
        errors.extend(f"{path}.{key}:required" for key in schema.get("required", []) if key not in value)
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}.{key}:additional" for key in value if key not in props)
        for key, item in value.items():
            if key in props:
                errors.extend(validate_schema(item, props[key], f"{path}.{key}"))
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(validate_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def _span_valid(source, value):
    return (isinstance(value, dict) and type(value.get("start")) is int and type(value.get("end")) is int
            and 0 <= value["start"] < value["end"] <= len(source)
            and source[value["start"]:value["end"]] == value.get("text"))


def _semantic_errors(frame, result, clauses, mentions, evidence):
    clause = clauses.get(frame["clause_id"])
    if not clause:
        return ["missing_clause"]
    text, errors = clause["text"], []
    if not frame["evidence_ids"] or any(x not in evidence for x in frame["evidence_ids"]):
        errors.append("missing_evidence")
    if frame["predicate_span"] is not None and not _span_valid(text, frame["predicate_span"]):
        errors.append("invalid_predicate_span")
    for role in ("subject", "object"):
        mid, eid = frame.get(role + "_mention_id"), frame.get(role + "_entity_id")
        if mid and (mid not in mentions or mentions[mid]["entity_id"] != eid):
            errors.append(f"invalid_{role}_identity")
    if any(mark in text for mark in ('"', '“', '”', '「', '」')):
        errors.append("quoted_scope_requires_review")
    rule = frame["extraction_rule"]
    if rule == "bounded_bank_event":
        event = bank_event(text)
        if not event or not event["supported"]:
            return errors + ["unsupported_bank_role"]
        modality = event["modality"] if event["modality"] != "asserted" else clause["assertion_status"]
        expected = {"subject": event["agent"]["text"], "object_text": event["patient"]["text"],
                    "predicate": event["predicate"], "voice": event["voice"], "polarity": event["polarity"],
                    "modality": modality, "target_concept": "FINANCIAL_BANK", "relation_type": "FINANCIAL_AFFORDANCE"}
        errors.extend("mismatch_" + key for key, value in expected.items() if frame[key] != value)
        for role, source_span in (("subject", event["agent"]), ("object", event["patient"])):
            mention = mentions.get(frame.get(role + "_mention_id"))
            if not mention or mention["clause_id"] != frame["clause_id"] or mention["span"] != source_span:
                errors.append("unanchored_" + role)
        should_apply = event["polarity"] == "positive" and modality in {"asserted", "corrective"}
        if frame["applied"] != should_apply:
            errors.append("application_state_mismatch")
    elif rule == "bounded_spatial":
        subject, obj = mentions.get(frame["subject_mention_id"]), mentions.get(frame["object_mention_id"])
        connector = SPATIAL_RE.search(text)
        if (not subject or not obj or not connector or bank_event(text)
                or not (subject["span"]["end"] <= connector.start() < obj["span"]["start"])
                or frame["predicate"] != "LOCATED_NEAR" or frame["target_concept"] != "RIVER_BANK"
                or frame["subject"] != subject["span"]["text"] or frame["object_text"] != obj["span"]["text"]):
            errors.append("unverified_spatial_attachment")
        if frame["applied"] and (frame["polarity"] != "positive" or frame["modality"] not in {"asserted", "corrective"}):
            errors.append("invalid_spatial_application")
    elif rule == "instance_reference":
        ref = next((r for r in result.get("reference_links", []) if r["link_id"] == frame["source_reference_id"]), None)
        antecedent = mentions.get(frame["object_mention_id"])
        if not ref or not antecedent:
            return errors + ["missing_reference"]
        if (ref.get("antecedent_entity_id") != frame["object_entity_id"]
                or ref.get("reference_mention_id") != frame["subject_mention_id"]
                or ref.get("antecedent_mention_id") != frame["object_mention_id"]
                or frame["target_clause_id"] != antecedent["clause_id"]
                or frame["target_concept"] != ref["concept"] or frame["predicate"] != "REFERS_TO"):
            errors.append("reference_identity_mismatch")
        if not any(r["clause_id"] == frame["clause_id"] and r["status"] == "resolved"
                   and frame["object_entity_id"] in r["resolved_entity_ids"] for r in result.get("reference_resolutions", [])):
            errors.append("unresolved_reference_promoted")
        old = evidence.get(ref["antecedent_evidence_id"], {})
        if not old.get("active") or old.get("vote", 0) <= 0:
            errors.append("inactive_reference_antecedent")
    elif rule == "ledger_supersession":
        target = clauses.get(frame["target_clause_id"])
        pairs = [(evidence.get(op["evidence_id"], {}), evidence.get(op["replacement_evidence_id"], {}))
                 for op in result["operations"] if op["operation"] == "SUPERSEDE"]
        valid = any(old.get("clause_id") == frame["target_clause_id"] and new.get("clause_id") == frame["clause_id"]
                    and old.get("target_id") == new.get("target_id") and not old.get("active", True)
                    and old.get("superseded_by") == new.get("evidence_id")
                    and old.get("evidence_id") in frame["evidence_ids"] and new.get("evidence_id") in frame["evidence_ids"]
                    for old, new in pairs)
        if not valid or not target or frame["object_text"] != target["text"] or frame["predicate"] != "REVISES":
            errors.append("ungrounded_revision_target")
        if clause["assertion_status"] != "corrective" or frame["modality"] != "corrective":
            errors.append("noncorrective_revision")
    else:
        errors.append("legacy_association_not_semantically_verified")
    return errors


def audit_result(result):
    schema_errors, graph_errors, rows = [], [], []
    clauses = {c["clause_id"]: c for c in result.get("clauses", [])}
    mentions = {m["mention_id"]: m for m in result.get("mentions", [])}
    entities = {e["entity_id"]: e for e in result.get("entities", [])}
    evidence = {e["evidence_id"]: e for e in result.get("evidence", [])}
    graph = result.get("claim_graph", {})
    node_ids = [n["node_id"] for n in graph.get("nodes", [])]
    node_types = {n["node_id"]: n["node_type"] for n in graph.get("nodes", [])}
    edge_ids = [e["edge_id"] for e in graph.get("edges", [])]
    if graph.get("invariants", {}).get("disabled") or not node_ids:
        graph_errors.append("graph_disabled_or_empty")
    if len(node_ids) != len(set(node_ids)) or len(edge_ids) != len(set(edge_ids)):
        graph_errors.append("duplicate_graph_ids")
    if any(e["source"] not in node_ids or e["target"] not in node_ids for e in graph.get("edges", [])):
        graph_errors.append("dangling_edge")
    for collection, key in (("mentions", "mention_id"), ("entities", "entity_id"), ("clauses", "clause_id"), ("evidence", "evidence_id")):
        ids = [item[key] for item in result.get(collection, [])]
        if len(ids) != len(set(ids)):
            schema_errors.append("duplicate_" + collection + "_ids")
    for mid in mentions:
        if node_types.get(mid) != "MENTION":
            graph_errors.append("missing_or_mistyped_mention:" + mid)
    for eid in entities:
        if node_types.get(eid) != "ENTITY_INSTANCE":
            graph_errors.append("missing_or_mistyped_entity:" + eid)
    for mention in mentions.values():
        clause = clauses.get(mention["clause_id"])
        if not clause or not _span_valid(clause["text"], mention["span"]):
            schema_errors.append(mention["mention_id"] + ":invalid_span")
        if mention["entity_id"] is not None and mention["entity_id"] not in entities:
            schema_errors.append(mention["mention_id"] + ":missing_entity")
    for clause in clauses.values():
        source_order = clause["source_order"]
        if not (0 <= source_order < len(result.get("inputs", []))) or clause["text"] not in result["inputs"][source_order]:
            schema_errors.append(clause["clause_id"] + ":source_mismatch")
    frame_ids = [f.get("frame_id") for f in result.get("relation_frames", []) if isinstance(f, dict)]
    if len(frame_ids) != len(set(frame_ids)):
        schema_errors.append("duplicate_frame_ids")
    for frame in result.get("relation_frames", []):
        errors = validate_schema(frame)
        if not errors:
            if node_types.get(frame["frame_id"]) != "RELATION_FRAME":
                graph_errors.append("missing_or_mistyped_frame:" + frame["frame_id"])
            for field, collection, key in (("source_relation_id", "relations", "relation_id"),
                                           ("source_reference_id", "reference_links", "link_id")):
                if frame[field] is not None and frame[field] not in {x[key] for x in result.get(collection, [])}:
                    errors.append(frame["frame_id"] + ":missing_" + field)
            for key in ("clause_id", "target_clause_id"):
                if frame[key] is not None and frame[key] not in clauses:
                    errors.append(frame["frame_id"] + ":missing_" + key)
        schema_errors.extend(errors)
        semantic_errors = errors or _semantic_errors(frame, result, clauses, mentions, evidence)
        rows.append({"frame_id": frame.get("frame_id") if isinstance(frame, dict) else None,
                     "semantic_status": "quarantined" if semantic_errors else "rule_checked",
                     "reasons": semantic_errors})
    expected_id = sha256(json.dumps(result.get("inputs", []), ensure_ascii=False).encode("utf-8")).hexdigest()
    if result.get("document_id") != expected_id:
        schema_errors.append("document_id_mismatch")
    return {"schema_valid": not schema_errors, "graph_valid": not graph_errors,
            "schema_errors": schema_errors, "graph_errors": graph_errors, "frames": rows,
            "rule_checked_count": sum(r["semantic_status"] == "rule_checked" for r in rows),
            "quarantined_count": sum(r["semantic_status"] == "quarantined" for r in rows),
            "meaning": "runtime rule consistency, not independently established semantic truth"}


def boundary_summary(result, audit):
    checked = {row["frame_id"] for row in audit["frames"] if row["semantic_status"] == "rule_checked"}
    positive = [f["frame_id"] for f in result["relation_frames"] if f["frame_id"] in checked
                and f["applied"] and f["polarity"] == "positive" and f["modality"] in {"asserted", "corrective"}]
    valid = audit["schema_valid"] and audit["graph_valid"]
    return {"mode": "observe_only", "observation_ready": bool(valid and checked),
            "schema_valid": audit["schema_valid"], "graph_valid": audit["graph_valid"],
            "positive_rule_checked_frame_ids": positive if valid else [],
            "inference_enabled": False, "inference_ready": False, "eligible_for_inference": [],
            "external_semantic_validation": "not_performed",
            "promotion_requirements": ["independent_semantic_evaluation", "consumer_acceptance_tests", "explicit_new_release"]}


def export_r1_observations(result, mode="observe_only"):
    if mode != "observe_only":
        raise ValueError("PLM-C2 v0.4 only exports observations; inference mode is not implemented")
    audit = audit_result(result)  # never trust cached flags on a caller-mutated result
    if not audit["schema_valid"] or not audit["graph_valid"]:
        raise ValueError("R1 export rejected: " + "; ".join(audit["schema_errors"] + audit["graph_errors"]))
    statuses = {r["frame_id"]: r for r in audit["frames"]}
    observations = []
    for frame in result["relation_frames"]:
        observation = deepcopy(frame)
        observation.update(observation_id=f"{result['document_id']}:{frame['frame_id']}",
                           semantic_status=statuses[frame["frame_id"]]["semantic_status"],
                           review_reasons=statuses[frame["frame_id"]]["reasons"], eligible_for_inference=False)
        observations.append(observation)
    return {"schema_version": 1, "producer_version": result["version"], "document_id": result["document_id"],
            "boundary": boundary_summary(result, audit), "observations": observations,
            "mentions": deepcopy(result["mentions"]), "entities": deepcopy(result["entities"]),
            "clauses": deepcopy(result["clauses"]), "evidence": deepcopy(result["evidence"])}
