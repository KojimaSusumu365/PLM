from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional
import re

from plm_c1.engine import RelationEvidence
from plm_c2_v02.engine import C2Config as C2V02Config
from plm_c2_v02.engine import PLMC2Engine as C2V02Engine
from plm_c2_v02.engine import ReferenceLink


@dataclass(frozen=True)
class C2Config(C2V02Config):
    use_relation_frames: bool = True
    use_generalized_revision_roles: bool = True
    use_extended_coreference: bool = True
    use_role_affordances: bool = True
    use_japanese_correction_scope: bool = True
    use_relation_aware_calibration: bool = True


@dataclass
class RelationFrame:
    frame_id: str
    clause_id: str
    relation_type: str
    subject: str
    predicate: str
    object_text: str
    voice: str
    polarity: str
    modality: str
    applied: bool
    target_concept: Optional[str] = None
    target_clause_id: Optional[str] = None
    source_relation_id: Optional[str] = None
    source_reference_id: Optional[str] = None


class PLMC2Engine(C2V02Engine):
    """PLM-C2 v0.3: relation-ready frames and bounded cross-clause reasoning."""

    REVISION_BOUNDARY = (
        r"[：:](?=\s*(?:revis\w*|amend\w*|updat\w*|correct\w*|"
        r"reclassif\w*|relab\w*|redesignat\w*|recategoriz\w*|"
        r"再分類|再指定|改訂|修正|訂正|更新))"
    )
    REVISION_ROLE_CUES = re.compile(
        r"(?:\breclassif(?:y|ies|ied|ication)\b|\brelab(?:el|els|eled|elled|eling|elling)\b|"
        r"\bredesignat(?:e|es|ed|ion)\b|\brecategoriz(?:e|es|ed|ation)\b|"
        r"\bchanged?\s+(?:the\s+)?(?:label|classification)\b|"
        r"再分類|再指定|分類変更|名称変更|改めて(?:分類|指定|判定))",
        re.IGNORECASE,
    )
    CONTRAST_BOUNDARY = (
        r"(?=\b(?:rather\b(?!\s+than\b)|instead\b(?!\s+of\b))|"
        r"(?:むしろ|正しくは|訂正すると|いや)(?![^、。；;]{0,8}(?:より|ではなく)))"
    )
    CONTRASTIVE_CUES = re.compile(
        r"^\s*(?:rather\b(?!\s+than\b)|instead\b(?!\s+of\b)|"
        r"むしろ|正しくは|訂正すると|いや)",
        re.IGNORECASE,
    )
    JAPANESE_MARKER_ONLY = re.compile(
        r"^\s*(?:むしろ|正しくは|訂正すると|いや)\s*$",
        re.IGNORECASE,
    )
    PAIR_REFERENCE_CUES = re.compile(
        r"\b(?P<english>the\s+(?:earlier|later|previous)\s+one)\b|"
        r"(?P<japanese>前者|後者)",
        re.IGNORECASE,
    )
    SINGULAR_REFERENCE_CUES = re.compile(
        r"\b(?P<english>it|this\s+one|that\s+one)\b|"
        r"(?P<japanese>それ|その個体)(?:は|が|を)?",
        re.IGNORECASE,
    )
    PLURAL_REFERENCE_CUES = re.compile(
        r"\b(?P<english>they|those\s+two)\b|(?P<japanese>それら|両者)(?:は|が|を)?",
        re.IGNORECASE,
    )
    ROLE_PREDICATE = re.compile(
        r"\b(?P<trigger>grant(?:s|ed|ing)?|award(?:s|ed|ing)?|"
        r"allocat(?:e|es|ed|ing)|invest(?:s|ed|ing)?|donat(?:e|es|ed|ing)|"
        r"subsidiz(?:e|es|ed|ing)|back(?:s|ed|ing)?|support(?:s|ed|ing)?)\b",
        re.IGNORECASE,
    )
    PASSIVE_ROLE_BANK = re.compile(
        r"\bbanks?\b[^.;!?]{0,24}\b(?:is|are|was|were|be|been|being|gets?|got)\s+"
        r"(?:granted|awarded|allocated|supported|backed|subsidized|funded|financed)\s+by\b",
        re.IGNORECASE,
    )
    RELATION_FRAME_REQUIRED_FIELDS = (
        "frame_id", "clause_id", "relation_type", "subject", "predicate",
        "object_text", "voice", "polarity", "modality", "applied",
    )

    def __init__(self, data_path: Optional[str] = None, config: Optional[C2Config] = None):
        self.c2_v03_config = config or C2Config()
        super().__init__(data_path=data_path, config=self.c2_v03_config)
        self._relation_frames: List[RelationFrame] = []
        self._extended_reference_count = 0
        self._role_affordance_count = 0

    def _classify_state(self, text: str):
        state = super()._classify_state(text)
        if (
            state == "asserted"
            and self.config.use_generalized_revision_roles
            and self.REVISION_ROLE_CUES.search(text)
        ):
            return "corrective"
        return state

    def segment(self, texts):
        clauses = super().segment(texts)
        if not self.config.use_japanese_correction_scope:
            return clauses
        for index, clause in enumerate(clauses[:-1]):
            following = clauses[index + 1]
            if (
                clause.source_id == following.source_id
                and clause.assertion_status == "corrective"
                and self.JAPANESE_MARKER_ONLY.fullmatch(clause.text)
                and following.assertion_status == "asserted"
            ):
                following.assertion_status = "corrective"
                following.discourse_state = "corrective"
                following.correction_target = self.config.use_correction
                self._operations.append({
                    "operation": "PROPAGATE_CORRECTION_SCOPE",
                    "from_clause_id": clause.clause_id,
                    "to_clause_id": following.clause_id,
                    "reason": "standalone Japanese correction marker",
                })
        return clauses

    def _append_role_affordance(self, clause, text, ambiguous_matches):
        if not (
            self.config.use_context
            and self.config.use_role_affordances
            and ambiguous_matches
        ):
            return
        bank_match = next(
            (match for match in ambiguous_matches if match["item"]["pattern"].lower() == "bank"),
            None,
        )
        if not bank_match:
            return
        trigger_match = self.ROLE_PREDICATE.search(text, bank_match["end"])
        if not trigger_match or trigger_match.start() - bank_match["end"] > 48:
            return
        link_text = text[bank_match["end"]:trigger_match.start()]
        passive = bool(self.PASSIVE_TAIL.search(link_text))
        trigger = trigger_match.group("trigger").lower()
        negated, depth = self._polarity(
            text, trigger_match.start(), trigger_match.end(), "FINANCIAL_BANK", trigger
        )
        hypothetical = clause.assertion_status == "hypothetical"
        applied = not passive and not negated and not hypothetical
        relation = RelationEvidence(
            relation_id=f"R{len(self._relations) + 1:04d}",
            clause_id=clause.clause_id,
            target_id=self._target_id(clause, "FINANCIAL_BANK"),
            relation_type="FINANCIAL_AFFORDANCE",
            ambiguous_pattern="bank",
            trigger=trigger,
            polarity=-1 if negated else 1,
            assertion_status=clause.assertion_status,
            applied=applied,
            reason=(
                "role-based institutional affordance" if applied else
                "passive role does not license subject affordance" if passive else
                "hypothetical role affordance" if hypothetical else
                "negated role affordance"
            ),
        )
        self._relations.append(relation)
        self._role_affordance_count += 1
        self._operations.append({
            "operation": "INFER_ROLE_AFFORDANCE",
            "relation_id": relation.relation_id,
            "predicate": trigger,
            "voice": "passive" if passive else "active",
            "applied": applied,
            "reason": relation.reason,
        })
        if applied:
            self._append_evidence(
                clause, f"[role:{trigger}]", "FINANCIAL_BANK", 1, 0.85,
                "role affordance", depth,
            )
            self._append_evidence(
                clause, f"[role:{trigger}]", "RIVER_BANK", -1, 0.45,
                "role contradiction", depth,
            )

    def _apply_context_relations(self, clause, text, ambiguous_matches):
        super()._apply_context_relations(clause, text, ambiguous_matches)
        self._append_role_affordance(clause, text, ambiguous_matches)

    def _relation_connected(self, text: str, boost_concept: str):
        if (
            boost_concept == "RIVER_BANK"
            and self.config.use_role_affordances
            and self.PASSIVE_ROLE_BANK.search(text)
        ):
            return False
        return super()._relation_connected(text, boost_concept)

    def _nearest_entity_mentions(self, reference_clause):
        prior_clauses = [
            clause for clause in self._clauses
            if (
                clause.source_order < reference_clause.source_order
                or (
                    clause.source_order == reference_clause.source_order
                    and clause.clause_id < reference_clause.clause_id
                )
            )
        ]
        for clause in reversed(prior_clauses):
            mentions = []
            seen = set()
            for evidence in self._ledger:
                if (
                    evidence.clause_id != clause.clause_id
                    or evidence.vote <= 0
                    or evidence.reason not in {"direct lexical support", "ambiguous lexical candidate"}
                    or self.concepts[evidence.concept]["domain"] != "entity"
                    or evidence.concept in seen
                ):
                    continue
                seen.add(evidence.concept)
                mentions.append(evidence)
            if mentions:
                return clause, mentions
        return None, []

    def _append_reference_resolution(self, clause, antecedent_clause, cue, antecedents):
        for antecedent in antecedents:
            evidence = self._append_evidence(
                clause, f"[reference:{cue}]", antecedent.concept, 1, 1.05,
                "bounded discourse coreference", 0,
            )
            link = ReferenceLink(
                link_id=f"Q{len(self._reference_links) + 1:04d}",
                clause_id=clause.clause_id,
                antecedent_clause_id=antecedent_clause.clause_id,
                cue=cue,
                concept=antecedent.concept,
                antecedent_evidence_id=antecedent.evidence_id,
            )
            self._reference_links.append(link)
            self._extended_reference_count += 1
            self._operations.append({
                "operation": "RESOLVE_DISCOURSE_REFERENCE",
                "reference_id": link.link_id,
                "clause_id": clause.clause_id,
                "antecedent_clause_id": antecedent_clause.clause_id,
                "resolution_evidence_id": evidence.evidence_id,
                "cue": cue,
                "concept": antecedent.concept,
            })

    def _resolve_extended_references(self):
        if not self.config.use_extended_coreference:
            return
        already_resolved = {link.clause_id for link in self._reference_links}
        for clause in self._clauses:
            if clause.clause_id in already_resolved:
                continue
            explicit_entity_evidence = any(
                evidence.clause_id == clause.clause_id
                and evidence.vote > 0
                and evidence.reason in {"direct lexical support", "ambiguous lexical candidate"}
                and self.concepts[evidence.concept]["domain"] == "entity"
                for evidence in self._ledger
            )
            if explicit_entity_evidence:
                continue
            text = self.normalize(clause.text)
            antecedent_clause, mentions = self._nearest_entity_mentions(clause)
            if not antecedent_clause:
                continue
            pair = self.PAIR_REFERENCE_CUES.search(text)
            singular = self.SINGULAR_REFERENCE_CUES.search(text)
            plural = self.PLURAL_REFERENCE_CUES.search(text)
            if pair and len(mentions) >= 2:
                cue = (pair.group("english") or pair.group("japanese")).lower()
                antecedent = mentions[0] if cue in {"the earlier one", "前者"} else mentions[-1]
                self._append_reference_resolution(clause, antecedent_clause, cue, [antecedent])
            elif singular and len(mentions) == 1:
                cue = (singular.group("english") or singular.group("japanese")).lower()
                self._append_reference_resolution(clause, antecedent_clause, cue, mentions)
            elif plural and len(mentions) >= 2:
                cue = (plural.group("english") or plural.group("japanese")).lower()
                self._append_reference_resolution(clause, antecedent_clause, cue, mentions)

    @staticmethod
    def _voice_for_relation(clause_text, trigger):
        match = re.search(re.escape(trigger), clause_text, re.IGNORECASE)
        if not match:
            return "n/a"
        before = clause_text[:match.start()]
        return "passive" if re.search(
            r"\b(?:is|are|was|were|be|been|being|gets?|got)\s*$", before, re.IGNORECASE
        ) else "active"

    def _build_relation_frames(self):
        if not self.config.use_relation_frames:
            return []
        frames = []
        clause_by_id = {clause.clause_id: clause for clause in self._clauses}
        for relation in self._relations:
            clause = clause_by_id[relation.clause_id]
            frames.append(RelationFrame(
                frame_id=f"F{len(frames) + 1:04d}",
                clause_id=relation.clause_id,
                relation_type=relation.relation_type,
                subject=relation.ambiguous_pattern,
                predicate=relation.trigger,
                object_text=clause.text,
                voice=self._voice_for_relation(clause.text, relation.trigger),
                polarity="positive" if relation.polarity > 0 else "negative",
                modality="hypothetical" if relation.assertion_status == "hypothetical" else "asserted",
                applied=relation.applied,
                target_concept=(
                    "FINANCIAL_BANK" if relation.relation_type == "FINANCIAL_AFFORDANCE"
                    else "RIVER_BANK" if relation.relation_type == "SPATIAL_ASSOCIATION"
                    else None
                ),
                source_relation_id=relation.relation_id,
            ))
        for reference in self._reference_links:
            frames.append(RelationFrame(
                frame_id=f"F{len(frames) + 1:04d}",
                clause_id=reference.clause_id,
                relation_type="COREFERENCE",
                subject=reference.cue,
                predicate="REFERS_TO",
                object_text=reference.concept,
                voice="n/a",
                polarity="positive",
                modality="asserted",
                applied=True,
                target_concept=reference.concept,
                target_clause_id=reference.antecedent_clause_id,
                source_reference_id=reference.link_id,
            ))
        for index, clause in enumerate(self._clauses):
            if clause.assertion_status != "corrective" or index == 0:
                continue
            previous = next(
                (
                    candidate for candidate in reversed(self._clauses[:index])
                    if candidate.instance_scope == clause.instance_scope
                ),
                None,
            )
            if previous:
                frames.append(RelationFrame(
                    frame_id=f"F{len(frames) + 1:04d}",
                    clause_id=clause.clause_id,
                    relation_type="REVISION",
                    subject=clause.clause_id,
                    predicate="REVISES",
                    object_text=previous.text,
                    voice="n/a",
                    polarity="positive",
                    modality="asserted",
                    applied=True,
                    target_clause_id=previous.clause_id,
                ))
        return frames

    def extract_evidence(self, texts):
        self._relation_frames = []
        self._extended_reference_count = 0
        self._role_affordance_count = 0
        evidence = super().extract_evidence(texts)
        self._resolve_extended_references()
        self._relation_frames = self._build_relation_frames()
        self._c1_diagnostics.update({
            "relation_frames": len(self._relation_frames),
            "extended_reference_resolutions": self._extended_reference_count,
            "role_affordance_items": self._role_affordance_count,
            "evidence_items": len(self._ledger),
            "active_evidence_items": sum(item.active for item in self._ledger),
        })
        return evidence

    def _select_domain(self, domain, scores):
        selection = super()._select_domain(domain, scores)
        if not self.config.use_relation_aware_calibration:
            return selection
        calibrated = dict(selection)
        v02_confidence = float(selection.get("selection_confidence", 0.0))
        calibrated["v02_selection_confidence"] = round(v02_confidence, 4)
        calibrated["selection_confidence"] = round(
            max(0.78, min(0.94, 0.86 + 0.20 * (v02_confidence - 0.82))),
            4,
        )
        calibrated["calibration"] = "relation-ready shrinkage toward conservative lower-bound prior"
        return calibrated

    def _extend_relation_graph(self, graph, relation_frames):
        if graph.get("invariants", {}).get("disabled"):
            return graph
        nodes = graph["nodes"]
        edges = graph["edges"]
        node_ids = {node["node_id"] for node in nodes}
        for frame in relation_frames:
            frame_id = frame["frame_id"]
            nodes.append({
                "node_id": frame_id,
                "node_type": "RELATION_FRAME",
                "label": frame["relation_type"],
                "attributes": {
                    key: value for key, value in frame.items()
                    if key not in {"frame_id", "clause_id"}
                },
            })
            node_ids.add(frame_id)
            links = [(frame["clause_id"], "YIELDS", frame_id)]
            if frame.get("source_relation_id"):
                links.append((frame_id, "FRAME_OF", frame["source_relation_id"]))
            if frame.get("source_reference_id"):
                links.append((frame_id, "FRAME_OF", frame["source_reference_id"]))
            if frame.get("target_concept"):
                links.append((frame_id, "MAPS_TO", f"CPT:{frame['target_concept']}"))
            if frame.get("target_clause_id"):
                relation = (
                    "SUPERSEDES_CLAUSE" if frame["relation_type"] == "REVISION"
                    else "REFERS_BACK_TO"
                )
                links.append((frame_id, relation, frame["target_clause_id"]))
            for source, relation, target in links:
                edges.append({
                    "edge_id": f"G{len(edges) + 1:04d}",
                    "source": source,
                    "relation": relation,
                    "target": target,
                    "attributes": {},
                })
        frame_ids = [frame["frame_id"] for frame in relation_frames]
        graph["schema_version"] = 2
        graph["invariants"].update({
            "unique_node_ids": len(node_ids) == len(nodes),
            "edges_resolve": all(
                edge["source"] in node_ids and edge["target"] in node_ids for edge in edges
            ),
            "unique_relation_frame_ids": len(frame_ids) == len(set(frame_ids)),
            "relation_frame_required_fields": all(
                all(field in frame for field in self.RELATION_FRAME_REQUIRED_FIELDS)
                for frame in relation_frames
            ),
        })
        return graph

    def analyze(self, texts):
        result = super().analyze(texts)
        result["version"] = "PLM-C2 v0.3"
        result["relation_frames"] = [asdict(frame) for frame in self._relation_frames]
        result["claim_graph"] = self._extend_relation_graph(
            result["claim_graph"], result["relation_frames"]
        )
        relation_types = sorted({frame.relation_type for frame in self._relation_frames})
        graph_invariants = result["claim_graph"]["invariants"]
        result["relation_contract"] = {
            "schema_version": 1,
            "required_fields": list(self.RELATION_FRAME_REQUIRED_FIELDS),
            "relation_types": relation_types,
            "frame_count": len(self._relation_frames),
            "ready_for_r1_experiment": (
                self.config.use_relation_frames
                and not graph_invariants.get("disabled", False)
                and all(graph_invariants.values())
            ),
        }
        result["diagnostics"].update({
            "relation_frames": len(self._relation_frames),
            "extended_reference_resolutions": self._extended_reference_count,
            "role_affordance_items": self._role_affordance_count,
            "claim_graph_nodes": len(result["claim_graph"]["nodes"]),
            "claim_graph_edges": len(result["claim_graph"]["edges"]),
        })
        return result
