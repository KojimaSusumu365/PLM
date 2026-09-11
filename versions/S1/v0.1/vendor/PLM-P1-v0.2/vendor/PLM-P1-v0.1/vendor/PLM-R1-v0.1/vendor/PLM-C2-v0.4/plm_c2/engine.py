from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
import json
import re

from plm_c1_v02.engine import PLMC1Engine as ContextEngine, RelationEvidence
from plm_c2_v03.engine import C2Config as OldConfig
from plm_c2_v03.engine import PLMC2Engine as OldEngine, RelationFrame as OldFrame
from .semantics import bank_event, match_span, SPATIAL_RE
from .coreference import InstanceCoreference


@dataclass(frozen=True)
class C2Config(OldConfig):
    use_semantic_roles: bool = True
    use_instance_coreference: bool = True
    use_grounded_revisions: bool = True
    use_empirical_calibration: bool = True


@dataclass
class RelationFrame(OldFrame):
    subject_mention_id: str | None = None
    object_mention_id: str | None = None
    subject_entity_id: str | None = None
    object_entity_id: str | None = None
    predicate_span: dict | None = None
    evidence_ids: list = field(default_factory=list)
    extraction_rule: str = "legacy_context"
    semantic_status: str = "unchecked"


class PLMC2Engine(InstanceCoreference, OldEngine):
    """v0.4: bounded semantic roles and an observation-only R1 boundary."""
    REVISION_BOUNDARY = OldEngine.REVISION_BOUNDARY.replace("reclassif", "reidentif\\w*|reclassif")
    REIDENTIFY = re.compile(r"\breidentif(?:y|ies|ied|ication)\b", re.I)
    LEXICAL_REASONS = {"direct lexical support", "ambiguous lexical candidate"}

    def __init__(self, data_path=None, config=None, calibration_path=None):
        super().__init__(data_path=data_path, config=config or C2Config())
        path = Path(calibration_path or Path(__file__).resolve().parents[1] / "data" / "calibration_v04_model.json")
        self.calibration_model = json.loads(path.read_text(encoding="utf-8")) if self.config.use_empirical_calibration and path.is_file() else None
        self._reset_semantics()

    def _reset_semantics(self):
        self._mentions, self._entities, self._reference_resolutions = [], [], []
        self._role_events = {}
        self._instance_mentions_built = False

    def _classify_state(self, text):
        state = super()._classify_state(text)
        if self.config.use_grounded_revisions and self.REIDENTIFY.search(text) and state == "asserted":
            return "corrective"
        return state

    def _has_event_shift(self, text):
        if self.config.use_instance_coreference and (self.PAIR_REFERENCE_CUES.search(text) or self.ORDERED_REFERENCE_CUES.search(text)):
            return False
        return super()._has_event_shift(text)

    def _apply_context_relations(self, clause, text, ambiguous_matches):
        if not self.config.use_semantic_roles:
            return super()._apply_context_relations(clause, text, ambiguous_matches)
        ContextEngine._apply_context_relations(self, clause, text, ambiguous_matches)
        if not self.config.use_context or not ambiguous_matches:
            return
        event = bank_event(clause.text)
        if not event:
            return
        if event["modality"] == "asserted" and clause.assertion_status != "asserted":
            event["modality"] = clause.assertion_status
        applied = (event["supported"] and event["polarity"] == "positive" and event["modality"] in {"asserted", "corrective"})
        relation = RelationEvidence(
            relation_id=f"R{len(self._relations) + 1:04d}", clause_id=clause.clause_id,
            target_id=self._target_id(clause, "FINANCIAL_BANK"), relation_type="FINANCIAL_AFFORDANCE",
            ambiguous_pattern="bank", trigger=event["predicate_span"]["text"],
            polarity=-1 if event["polarity"] == "negative" else 1,
            assertion_status=event["modality"], applied=applied, reason=event["reason"],
        )
        self._relations.append(relation)
        self._role_events[relation.relation_id] = event
        self._operations.append({"operation": "EXTRACT_SEMANTIC_ROLE", "relation_id": relation.relation_id,
                                 "voice": event["voice"], "bank_role": event["bank_role"], "applied": applied})
        if applied:
            self._append_evidence(clause, f"[role:{event['predicate']}]", "FINANCIAL_BANK", 1, .85, "semantic role support")
            self._append_evidence(clause, f"[role:{event['predicate']}]", "RIVER_BANK", -1, .45, "semantic role contradiction")

    def _relation_connected(self, text, boost_concept):
        if self.config.use_semantic_roles and boost_concept == "RIVER_BANK" and bank_event(text):
            return False
        return super()._relation_connected(text, boost_concept)

    def _apply_corrections(self):
        if not self.config.use_grounded_revisions:
            return super()._apply_corrections()
        for clause in self._clauses:
            if clause.assertion_status == "retracted" and self.config.use_residual:
                for evidence in self._ledger:
                    if evidence.clause_id == clause.clause_id and evidence.active:
                        evidence.active, evidence.effective_weight, evidence.assertion_status = False, 0., "retracted"
                        self._operations.append({"operation": "RETRACT", "evidence_id": evidence.evidence_id})
            if not clause.correction_target:
                continue
            replacements = {}
            for evidence in self._ledger:
                if evidence.clause_id == clause.clause_id and evidence.vote > 0 and evidence.reason in self.LEXICAL_REASONS:
                    replacements.setdefault(self.concepts[evidence.concept]["domain"], evidence)
            for replacement in replacements.values():
                for target in self._ledger:
                    if not (target.active and target.vote > 0 and target.target_id == replacement.target_id
                            and target.concept != replacement.concept
                            and (target.source_order, target.clause_id) < (replacement.source_order, replacement.clause_id)):
                        continue
                    self._operations.append({"operation": "SUPERSEDE" if self.config.use_residual else "SUPERSEDE_SKIPPED",
                                             "evidence_id": target.evidence_id, "concept": target.concept,
                                             "replacement_evidence_id": replacement.evidence_id,
                                             "replacement_concept": replacement.concept,
                                             "residual_removed": target.effective_weight if self.config.use_residual else 0.})
                    if self.config.use_residual:
                        target.active, target.effective_weight, target.assertion_status = False, 0., "superseded"
                        target.superseded_by = replacement.evidence_id

    def _build_relation_frames(self):
        if not self.config.use_relation_frames:
            return []
        self._build_instance_mentions()
        clauses = {c.clause_id: c for c in self._clauses}
        evidence_by_id = {e.evidence_id: e for e in self._ledger}
        references, frames = {r.link_id: r for r in self._reference_links}, []
        for old in super()._build_relation_frames():
            if old.relation_type == "REVISION" and self.config.use_grounded_revisions:
                continue
            frame = RelationFrame(**asdict(old))
            clause = clauses[frame.clause_id]
            event = self._role_events.get(frame.source_relation_id)
            if event:
                agent = self._mention(clause, event["agent"], ["FINANCIAL_BANK"] if event["bank_role"] == "agent" else [], kind="argument") if event["agent"] else None
                patient = self._mention(clause, event["patient"], kind="argument")
                frame.subject = event["agent"]["text"] if event["agent"] else ""
                frame.object_text, frame.predicate, frame.predicate_span = event["patient"]["text"], event["predicate"], event["predicate_span"]
                frame.voice, frame.polarity, frame.modality = event["voice"], event["polarity"], event["modality"]
                frame.extraction_rule = "bounded_bank_event"
                if agent:
                    frame.subject_mention_id, frame.subject_entity_id = agent["mention_id"], agent["entity_id"]
                frame.object_mention_id, frame.object_entity_id = patient["mention_id"], patient["entity_id"]
            elif frame.relation_type == "COREFERENCE" and self.config.use_instance_coreference:
                ref = references[frame.source_reference_id]
                frame.subject_mention_id, frame.object_mention_id = ref.reference_mention_id, ref.antecedent_mention_id
                frame.subject_entity_id = frame.object_entity_id = ref.antecedent_entity_id
                frame.evidence_ids, frame.extraction_rule, frame.modality = [ref.antecedent_evidence_id], "instance_reference", clause.assertion_status
            elif frame.relation_type == "SPATIAL_ASSOCIATION":
                bank, trigger = re.search(r"\bbanks?\b", clause.text, re.I), re.search(re.escape(old.predicate), clause.text, re.I)
                connector = SPATIAL_RE.search(clause.text)
                if bank and trigger and connector and not bank_event(clause.text):
                    agent = self._mention(clause, match_span(clause.text, bank), ["RIVER_BANK"], kind="argument")
                    patient = self._mention(clause, match_span(clause.text, trigger), kind="argument")
                    frame.subject, frame.object_text = agent["span"]["text"], patient["span"]["text"]
                    frame.subject_mention_id, frame.subject_entity_id = agent["mention_id"], agent["entity_id"]
                    frame.object_mention_id, frame.object_entity_id = patient["mention_id"], patient["entity_id"]
                    frame.predicate, frame.predicate_span = "LOCATED_NEAR", match_span(clause.text, connector)
                    frame.voice, frame.extraction_rule = "n/a", "bounded_spatial"
            if not frame.evidence_ids:
                frame.evidence_ids = [e.evidence_id for e in self._ledger if e.clause_id == clause.clause_id]
            frames.append(frame)
        if self.config.use_grounded_revisions:
            grouped = {}
            for operation in self._operations:
                if operation["operation"] != "SUPERSEDE":
                    continue
                old, new = evidence_by_id[operation["evidence_id"]], evidence_by_id[operation["replacement_evidence_id"]]
                grouped.setdefault((new.clause_id, old.clause_id), []).extend([old.evidence_id, new.evidence_id])
            for (clause_id, old_clause_id), ids in grouped.items():
                frames.append(RelationFrame(frame_id="", clause_id=clause_id, relation_type="REVISION", subject=clause_id,
                    predicate="REVISES", object_text=clauses[old_clause_id].text, voice="n/a", polarity="positive",
                    modality="corrective", applied=True, target_clause_id=old_clause_id, evidence_ids=sorted(set(ids)),
                    extraction_rule="ledger_supersession"))
        for index, frame in enumerate(frames, 1):
            frame.frame_id = f"F{index:04d}"
        return frames

    def extract_evidence(self, texts):
        self._reset_semantics()
        super().extract_evidence(texts)
        return self._ledger

    def _select_domain(self, domain, scores):
        selection = dict(super()._select_domain(domain, scores))
        selected, risks = selection["selected"], []
        if domain == "entity" and any(r["status"] != "resolved" for r in self._reference_resolutions):
            risks.append("unresolved_instance_reference")
        events = list(self._role_events.values()) if domain == "place" else []
        if any(not e["supported"] for e in events):
            risks.append("unsupported_role")
        signal = .65 if selected == "UNRESOLVED" else .45 if risks else .80 if events else .90 if any(
            e.active and e.concept == selected and e.vote > 0 and e.reason in self.LEXICAL_REASONS for e in self._ledger) else .55
        selection.update(legacy_selection_confidence=selection["selection_confidence"], reliability_signal=signal,
                         risk_flags=risks, confidence_target="correctness_of_selected_label_including_abstention",
                         selection_confidence=signal, calibration="uncalibrated_rule_signal")
        if self.calibration_model:
            bins = self.calibration_model["bins"]
            found = next((b for b in bins if signal <= b["upper_signal"]), bins[-1])
            selection.update(selection_confidence=found["probability"], calibration="heldout_calibration_isotonic_beta_smoothed",
                             calibration_samples=found["samples"])
        return selection

    def _extend_relation_graph(self, graph, frames):
        graph = super()._extend_relation_graph(graph, frames)
        if graph["invariants"].get("disabled"):
            return graph
        nodes, edges = graph["nodes"], graph["edges"]
        for node in nodes:
            if node["node_type"] == "ENTITY":
                node["node_type"] = "TARGET_SCOPE"
        for entity in self._entities:
            nodes.append({"node_id": entity["entity_id"], "node_type": "ENTITY_INSTANCE", "label": entity["entity_id"], "attributes": entity})
        def edge(source, relation, target):
            if target:
                edges.append({"edge_id": f"G{len(edges) + 1:04d}", "source": source, "relation": relation, "target": target, "attributes": {}})
        for mention in self._mentions:
            nodes.append({"node_id": mention["mention_id"], "node_type": "MENTION", "label": mention["span"]["text"], "attributes": mention})
            edge(mention["clause_id"], "HAS_MENTION", mention["mention_id"])
            edge(mention["mention_id"], "DENOTES", mention["entity_id"])
        for frame in frames:
            edge(frame["frame_id"], "HAS_SUBJECT", frame.get("subject_mention_id"))
            edge(frame["frame_id"], "HAS_OBJECT", frame.get("object_mention_id"))
            for evidence_id in frame["evidence_ids"]:
                edge(frame["frame_id"], "DERIVED_FROM", evidence_id)
        ids = [n["node_id"] for n in nodes]
        graph["schema_version"] = 3
        graph["invariants"].update(unique_node_ids=len(ids) == len(set(ids)), edges_resolve=all(e["source"] in ids and e["target"] in ids for e in edges))
        return graph

    def analyze(self, texts):
        from .audit import audit_result, boundary_summary
        result = super().analyze(texts)
        result["version"] = "PLM-C2 v0.4"
        result["document_id"] = sha256(json.dumps(result["inputs"], ensure_ascii=False).encode("utf-8")).hexdigest()
        result["mentions"], result["entities"], result["reference_resolutions"] = self._mentions, self._entities, self._reference_resolutions
        result["semantic_audit"] = audit_result(result)
        statuses = {row["frame_id"]: row["semantic_status"] for row in result["semantic_audit"]["frames"]}
        for frame in result["relation_frames"]:
            frame["semantic_status"] = statuses.get(frame["frame_id"], "quarantined")
        for node in result["claim_graph"]["nodes"]:
            if node["node_type"] == "RELATION_FRAME":
                node["attributes"]["semantic_status"] = statuses.get(node["node_id"], "quarantined")
        result["r1_boundary"] = boundary_summary(result, result["semantic_audit"])
        result["relation_contract"] = {"schema_version": 2, "frame_count": len(result["relation_frames"]),
            "schema_valid": result["semantic_audit"]["schema_valid"], "observation_ready": result["r1_boundary"]["observation_ready"],
            "inference_ready": False, "ready_for_r1_experiment": result["r1_boundary"]["observation_ready"],
            "readiness_scope": "observation_only; no inference promotion"}
        return result
