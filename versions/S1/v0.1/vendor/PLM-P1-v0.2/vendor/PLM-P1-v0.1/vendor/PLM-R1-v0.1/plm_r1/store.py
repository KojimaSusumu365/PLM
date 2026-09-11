"""Transactional, immutable-content observations with append-only review notes."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
from .contract import canonical, digest, require, validate_envelope, ERROR_TYPES
from .producer import export_observations


class ObservationStore:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY, envelope_hash TEXT NOT NULL, envelope TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT NOT NULL, revision TEXT NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(document_id),
            PRIMARY KEY(source_id, revision));
        CREATE TABLE IF NOT EXISTS contexts (
            document_id TEXT PRIMARY KEY REFERENCES documents(document_id),
            context_hash TEXT NOT NULL, analysis TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews (
            event_id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(document_id),
            payload TEXT NOT NULL, recorded_at TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS reviews_no_update BEFORE UPDATE ON reviews
            BEGIN SELECT RAISE(ABORT, 'append-only reviews'); END;
        CREATE TRIGGER IF NOT EXISTS reviews_no_delete BEFORE DELETE ON reviews
            BEGIN SELECT RAISE(ABORT, 'append-only reviews'); END;
        CREATE TRIGGER IF NOT EXISTS documents_no_update BEFORE UPDATE ON documents
            BEGIN SELECT RAISE(ABORT, 'immutable observation'); END;
        CREATE TRIGGER IF NOT EXISTS documents_no_delete BEFORE DELETE ON documents
            BEGIN SELECT RAISE(ABORT, 'immutable observation'); END;
        """)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.db.close()

    def ingest_analysis(self, analysis, *, source_id, revision="1"):
        # The sidecar retains raw input, selections, unresolved references and operations.
        return self.ingest(export_observations(analysis), source_id=source_id,
                           revision=revision, analysis=analysis)

    def ingest(self, envelope, *, source_id, revision="1", analysis=None, mode="observe_only"):
        require(mode == "observe_only", "R1 v0.1 has no inference mode")
        require(type(source_id) is str and source_id.strip() and type(revision) is str and revision.strip(),
                "Nonempty external source_id and revision required")
        env = deepcopy(envelope)
        receipt = validate_envelope(env)
        if analysis is not None:
            require(export_observations(analysis) == env, "Analysis/envelope mismatch")
            receipt.update(content_hash_verified=True, semantic_validation="C2_rules_replayed_not_independent")
        doc, env_hash = env["document_id"], digest(env)
        context_hash = digest(analysis) if analysis is not None else None
        with self.db:
            existing_source = self.db.execute("SELECT document_id FROM sources WHERE source_id=? AND revision=?",
                                              (source_id, revision)).fetchone()
            require(existing_source is None or existing_source[0] == doc,
                    "Source revision conflict; provide a new revision, never overwrite")
            existing = self.db.execute("SELECT envelope_hash FROM documents WHERE document_id=?", (doc,)).fetchone()
            require(existing is None or existing[0] == env_hash, "Same content ID has different observation payload")
            existing_context = self.db.execute("SELECT context_hash FROM contexts WHERE document_id=?", (doc,)).fetchone()
            require(analysis is None or existing_context is None or existing_context[0] == context_hash,
                    "Same content has conflicting analysis context")
            if existing is None:
                self.db.execute("INSERT INTO documents VALUES (?,?,?)", (doc, env_hash, canonical(env)))
            if existing_source is None:
                self.db.execute("INSERT INTO sources VALUES (?,?,?)", (source_id, revision, doc))
            if analysis is not None and existing_context is None:
                self.db.execute("INSERT INTO contexts VALUES (?,?,?)", (doc, context_hash, canonical(analysis)))
        return dict(receipt, document_id=doc, envelope_hash=env_hash,
                    document_created=existing is None, source_link_created=existing_source is None,
                    context_added=analysis is not None and existing_context is None)

    def review(self, *, event_id, document_id, target_id, reviewer_id, decision, error_types, note):
        """A reviewer opinion does not change producer observations or enable inference."""
        require(decision in {"needs_review", "agrees_with_observation", "disagrees", "uncertain"}, "Unsupported review decision")
        require(type(error_types) is list and all(x in ERROR_TYPES for x in error_types), "Unknown error taxonomy")
        require(all(type(x) is str and x.strip() for x in (event_id, reviewer_id, note)), "Review identifiers and note required")
        row = self.db.execute("SELECT envelope FROM documents WHERE document_id=?", (document_id,)).fetchone()
        require(row is not None, "Unknown review document")
        env = json.loads(row[0])
        require(target_id == document_id or target_id in {f["observation_id"] for f in env["observations"]}, "Unknown review target")
        payload = dict(event_id=event_id, document_id=document_id, target_id=target_id,
                       reviewer_id=reviewer_id, decision=decision, error_types=error_types,
                       note=note, eligible_for_inference=False)
        encoded = canonical(payload)
        with self.db:
            old = self.db.execute("SELECT payload FROM reviews WHERE event_id=?", (event_id,)).fetchone()
            require(old is None or old[0] == encoded, "Review event ID conflict; append a new event")
            if old is None:
                self.db.execute("INSERT INTO reviews VALUES (?,?,?,?)",
                                (event_id, document_id, encoded, datetime.now(timezone.utc).isoformat()))
        return {"event_created": old is None, "eligible_for_inference": False}

    def ledger(self):
        documents = []
        for doc, env_hash, encoded in self.db.execute("SELECT * FROM documents ORDER BY document_id"):
            env = json.loads(encoded)
            context_row = self.db.execute("SELECT context_hash,analysis FROM contexts WHERE document_id=?", (doc,)).fetchone()
            context = json.loads(context_row[1]) if context_row else None
            clauses = {c["clause_id"]: c for c in env["clauses"]}
            evidence = {e["evidence_id"]: e for e in env["evidence"]}
            observations = []
            for frame in env["observations"]:
                status = frame["semantic_status"]
                flags = ["producer_" + status, "not_a_fact", "review_pending"]
                if frame["polarity"] == "negative":
                    flags.append("negative")
                if frame["modality"] != "asserted":
                    flags.append(frame["modality"])
                observations.append({"observation_id": frame["observation_id"], "original_frame": frame,
                                     "source_clause": clauses[frame["clause_id"]],
                                     "target_clause": clauses.get(frame.get("target_clause_id")),
                                     "qualified_subject_entity": doc + ":" + frame["subject_entity_id"] if frame["subject_entity_id"] else None,
                                     "qualified_object_entity": doc + ":" + frame["object_entity_id"] if frame["object_entity_id"] else None,
                                     "evidence": [evidence[eid] for eid in frame["evidence_ids"]],
                                     "review_flags": flags, "eligible_for_inference": False})
            notices = []
            if not observations:
                notices.append("no_relation_extracted_not_proof_of_absence")
            if not context:
                notices.append("context_missing_raw_input_selections_unresolved_references_operations")
            else:
                for resolution in context.get("reference_resolutions", []):
                    if resolution["status"] != "resolved":
                        notices.append("reference_" + resolution["status"] + ":" + resolution["clause_id"])
                if not any(f["original_frame"]["semantic_status"] == "rule_checked" for f in observations):
                    notices.append("no_rule_checked_relation_review_original_text")
            reviews = [dict(json.loads(payload), recorded_at=timestamp) for payload, timestamp in
                       self.db.execute("SELECT payload,recorded_at FROM reviews WHERE document_id=? ORDER BY rowid", (doc,))]
            reviewed_targets = {r["target_id"] for r in reviews}
            for observation in observations:
                if observation["observation_id"] in reviewed_targets:
                    observation["review_flags"].remove("review_pending")
                    observation["review_flags"].append("review_recorded_opinion_only")
            documents.append({"document_id": doc, "envelope_hash": env_hash,
                              "sources": [dict(source_id=s, revision=r) for s, r in self.db.execute(
                                  "SELECT source_id,revision FROM sources WHERE document_id=? ORDER BY source_id,revision", (doc,))],
                              "raw_inputs": context.get("inputs") if context else None,
                              "producer_selections": context.get("selections") if context else None,
                              "reference_resolutions": context.get("reference_resolutions") if context else None,
                              "operations": context.get("operations") if context else None,
                              "context_hash": context_row[0] if context_row else None,
                              "mentions": env["mentions"], "entities": env["entities"], "evidence": env["evidence"],
                              "producer_boundary": env["boundary"], "notices": notices,
                              "observations": observations, "reviews": reviews})
        return {"version": "PLM-R1 v0.1", "mode": "observe_only", "inference_enabled": False,
                "independent_semantic_evaluation": "not_performed", "unique_content_count": len(documents),
                "source_revision_count": sum(len(d["sources"]) for d in documents),
                "observation_count": sum(len(d["observations"]) for d in documents),
                "independent_evidence_count": None, "documents": documents}


def markdown(ledger):
    import html
    def safe(value):
        return html.escape(str(value)).replace("|", "&#124;").replace("\n", "<br>").replace("`", "&#96;")
    lines = ["# PLM-R1 v0.1 観察レビュー台帳", "",
             "推論は無効。rule_checkedはC2の規則整合性であり、独立評価済みの事実を意味しません。",
             "同一内容は1件として集計し、別出典・改訂との対応は別に保持します。", "",
             f"内容 {ledger['unique_content_count']} 件 / 出典・改訂 {ledger['source_revision_count']} 件 / 観察 {ledger['observation_count']} 件。", ""]
    for doc in ledger["documents"]:
        lines.extend(["## " + safe(", ".join(s["source_id"] + "@" + s["revision"] for s in doc["sources"])), "",
                      "内容ID: " + doc["document_id"], ""])
        if doc["raw_inputs"] is not None:
            lines.extend(["原文: " + safe(" / ".join(doc["raw_inputs"])), ""])
        for notice in doc["notices"]:
            lines.extend(["注意: " + safe(notice), ""])
        for domain, selection in (doc["producer_selections"] or {}).items():
            if domain in {"entity", "place"}:
                lines.extend([f"C2分類（Relationの真偽とは別）: {safe(domain)} → {safe(selection['selected'])}; selection_confidence={selection.get('selection_confidence')}", ""])
        for obs in doc["observations"]:
            f = obs["original_frame"]
            lines.extend(["### " + f["frame_id"] + " — " + f["relation_type"], "",
                          "節: " + safe(obs["source_clause"]["text"]), "",
                          f"主体: {safe(f['subject'])} / 述語: {safe(f['predicate'])} / 対象: {safe(f['object_text'])}", "",
                          f"状態: {safe(f['semantic_status'])} / {f['polarity']} / {f['modality']} / {f['voice']}; 推論不可。", "",
                          "主体個体: " + safe(obs["qualified_subject_entity"]) + " / 対象個体: " + safe(obs["qualified_object_entity"]), "",
                          "規則・隔離理由: " + safe(f["extraction_rule"] + " / " + ", ".join(f["review_reasons"])), ""])
            for e in obs["evidence"]:
                lines.extend([f"根拠 {safe(e['evidence_id'])}: {safe(e['source_text'])}; active={e['active']}; superseded_by={safe(e.get('superseded_by'))}", ""])
        for review in doc["reviews"]:
            lines.extend(["レビュー記録: " + safe(review["event_id"] + " / " + review["reviewer_id"] + " / " + review["decision"]), "",
                          safe(review["note"]), ""])
    return "\n".join(lines) + "\n"
