"""Structural transport validation, explicitly not independent semantic validation."""
import json
import re
from hashlib import sha256
from .producer import VENDOR

FRAME_SCHEMA = json.loads((VENDOR / "RELATION_SCHEMA.json").read_text(encoding="utf-8"))
ERROR_TYPES = {"subject_role", "object_role", "predicate", "polarity", "modality",
               "voice", "coreference", "revision_target", "unknown_predicate",
               "missing_relation", "spurious_relation", "span", "classification",
               "source_quality", "other"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def content_id(inputs):
    # C2's content identity uses default JSON separators (not our transport hash).
    return sha256(json.dumps(inputs, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError("Non-finite JSON number: " + value)
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=pairs, parse_constant=bad_constant)


def _schema(value, schema, path):
    expected = schema.get("type")
    if expected:
        types = expected if isinstance(expected, list) else [expected]
        matches = {"null": value is None, "object": type(value) is dict,
                   "array": type(value) is list, "string": type(value) is str,
                   "boolean": type(value) is bool, "integer": type(value) is int,
                   "number": type(value) in (int, float)}
        require(any(matches.get(t, False) for t in types), path + ": type")
    if "enum" in schema:
        require(value in schema["enum"], path + ": enum")
    if isinstance(value, str) and "pattern" in schema:
        require(re.search(schema["pattern"], value) is not None, path + ": pattern")
    if type(value) in (int, float) and "minimum" in schema:
        require(value >= schema["minimum"], path + ": minimum")
    if isinstance(value, dict):
        require(set(schema.get("required", [])) <= set(value), path + ": required")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            require(set(value) <= set(props), path + ": unknown property")
        for key in value.keys() & props.keys():
            _schema(value[key], props[key], path + "." + key)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _schema(item, schema["items"], f"{path}[{i}]")


def _index(rows, key):
    require(type(rows) is list, key + ": list required")
    result = {}
    for row in rows:
        require(type(row) is dict and type(row.get(key)) is str and row[key], key + ": missing id")
        require(row[key] not in result, key + ": duplicate id")
        result[row[key]] = row
    return result


def _span(span, text, label):
    require(type(span) is dict and set(span) == {"start", "end", "text"}, label + ": span fields")
    start, end = span["start"], span["end"]
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), label + ": bounds")
    require(text[start:end] == span["text"], label + ": text mismatch")


def validate_envelope(env):
    # Reject non-JSON types/NaN before touching state.
    canonical(env)
    required = {"schema_version", "producer_version", "document_id", "boundary",
                "observations", "mentions", "entities", "clauses", "evidence"}
    require(type(env) is dict and set(env) == required, "Unsupported envelope fields")
    require(type(env["schema_version"]) is int and env["schema_version"] == 1, "Unsupported schema")
    require(env["producer_version"] == "PLM-C2 v0.4", "Unsupported producer")
    doc = env["document_id"]
    require(type(doc) is str and re.fullmatch(r"[0-9a-f]{64}", doc), "Invalid document_id")
    boundary = env["boundary"]
    require(type(boundary) is dict, "boundary must be object")
    require(boundary.get("mode") == "observe_only" and boundary.get("inference_enabled") is False
            and boundary.get("inference_ready") is False and boundary.get("eligible_for_inference") == [],
            "Inference boundary violation")
    require(boundary.get("schema_valid") is True and boundary.get("graph_valid") is True, "Producer reported invalid transport")
    require(boundary.get("external_semantic_validation") == "not_performed", "Unsupported semantic validation claim")
    clauses = _index(env["clauses"], "clause_id")
    entities = _index(env["entities"], "entity_id")
    mentions = _index(env["mentions"], "mention_id")
    evidence = _index(env["evidence"], "evidence_id")
    frames = _index(env["observations"], "frame_id")
    for clause in clauses.values():
        require(type(clause.get("text")) is str and type(clause.get("source_order")) is int
                and clause["source_order"] >= 0 and type(clause.get("source_id")) is str, "Invalid clause")
    for mention in mentions.values():
        require(mention.get("clause_id") in clauses, "Dangling mention clause")
        clause = clauses[mention["clause_id"]]
        _span(mention.get("span"), clause["text"], "mention")
        require(mention.get("entity_id") is None or mention["entity_id"] in entities, "Dangling mention entity")
        require(mention.get("source_id") == clause["source_id"], "Mention source mismatch")
        require(all(eid in evidence for eid in mention.get("evidence_ids", [])), "Dangling mention evidence")
    for item in evidence.values():
        require(item.get("clause_id") in clauses, "Dangling evidence clause")
        clause = clauses[item["clause_id"]]
        require(item.get("source_id") == clause["source_id"] and item.get("source_order") == clause["source_order"], "Evidence source mismatch")
        require(type(item.get("active")) is bool, "Evidence active must be boolean")
        require(item.get("superseded_by") is None or item["superseded_by"] in evidence, "Dangling supersession")
        if item.get("superseded_by"):
            require(not item["active"] and item["superseded_by"] != item["evidence_id"], "Invalid supersession")
        seen = set()
        cursor = item
        while cursor.get("superseded_by"):
            require(cursor["evidence_id"] not in seen, "Cyclic supersession")
            seen.add(cursor["evidence_id"])
            require(cursor["superseded_by"] in evidence, "Dangling supersession chain")
            cursor = evidence[cursor["superseded_by"]]
    for frame in frames.values():
        extras = {"observation_id", "review_reasons", "eligible_for_inference"}
        _schema({k: v for k, v in frame.items() if k not in extras}, FRAME_SCHEMA, "frame")
        require(frame.get("observation_id") == doc + ":" + frame["frame_id"], "Observation identity mismatch")
        require(frame.get("eligible_for_inference") is False, "Observation inference violation")
        require(type(frame.get("review_reasons")) is list and all(type(x) is str for x in frame["review_reasons"]), "Invalid reasons")
        require(frame["clause_id"] in clauses, "Dangling frame clause")
        require(frame.get("target_clause_id") is None or frame["target_clause_id"] in clauses, "Dangling target clause")
        for role in ("subject", "object"):
            mid, eid = frame[role + "_mention_id"], frame[role + "_entity_id"]
            require(mid is None or mid in mentions, "Dangling role mention")
            require(eid is None or eid in entities, "Dangling role entity")
            if mid is not None:
                require(mentions[mid]["entity_id"] == eid, "Role entity mismatch")
                expected_clause = frame.get("target_clause_id") if role == "object" and frame["relation_type"] == "COREFERENCE" else frame["clause_id"]
                require(mentions[mid]["clause_id"] == expected_clause, "Role clause mismatch")
        require(len(frame["evidence_ids"]) == len(set(frame["evidence_ids"])) and all(x in evidence for x in frame["evidence_ids"]), "Invalid evidence references")
        if frame["predicate_span"] is not None:
            _span(frame["predicate_span"], clauses[frame["clause_id"]]["text"], "predicate")
    positive = [f["frame_id"] for f in frames.values() if f["semantic_status"] == "rule_checked"
                and f["applied"] and f["polarity"] == "positive" and f["modality"] in {"asserted", "corrective"}]
    require(boundary.get("positive_rule_checked_frame_ids") == positive, "Inconsistent producer positive list")
    require(type(boundary.get("observation_ready")) is bool and boundary["observation_ready"] ==
            any(f["semantic_status"] == "rule_checked" for f in frames.values()), "Inconsistent producer readiness")
    return {"transport_validated": True, "semantic_validation": "producer_claim_only",
            "graph_independently_validated": False, "content_hash_verified": False,
            "inference_enabled": False}
