from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional
import re

from plm_c1.engine import Clause, RelationEvidence
from plm_c2_v01.engine import C2Config as C2V01Config
from plm_c2_v01.engine import PLMC2Engine as C2V01Engine


@dataclass(frozen=True)
class C2Config(C2V01Config):
    use_structural_revision_boundaries: bool = True
    use_contrastive_corrections: bool = True
    use_ordered_coreference: bool = True
    use_agentive_affordances: bool = True
    use_conservative_calibration: bool = True


@dataclass
class ReferenceLink:
    link_id: str
    clause_id: str
    antecedent_clause_id: str
    cue: str
    concept: str
    antecedent_evidence_id: str


class PLMC2Engine(C2V01Engine):
    """PLM-C2 v0.2: bounded discourse resolution over the v0.1 claim graph."""

    REVISION_BOUNDARY = (
        r":(?=\s*(?:revised|amended|updated|corrected|reclassified|revision)\b)"
    )
    CONTRAST_BOUNDARY = r"(?=\b(?:rather\b(?!\s+than\b)|instead\b(?!\s+of\b)))"
    CONTRASTIVE_CUES = re.compile(
        r"^\s*(?:rather\b(?!\s+than\b)|instead\b(?!\s+of\b))",
        re.IGNORECASE,
    )
    ORDERED_REFERENCE_CUES = re.compile(
        r"\b(?:(?:the\s+)?(?P<former_latter>former|latter)|"
        r"the\s+(?P<ordinal>first|second))\b",
        re.IGNORECASE,
    )
    AGENTIVE_TRIGGER = re.compile(
        r"\b(?P<trigger>sponsor(?:s|ed|ing)?|fund(?:s|ed|ing)?|"
        r"financ(?:e|es|ed|ing)|underw(?:rite|rites|rote|riting)|"
        r"lend(?:s|ing)?|lent)\b",
        re.IGNORECASE,
    )
    PASSIVE_TAIL = re.compile(
        r"\b(?:is|are|was|were|be|been|being|gets?|got)\s*$",
        re.IGNORECASE,
    )
    PASSIVE_AGENTIVE_BANK = re.compile(
        r"\bbanks?\b[^.;!?]{0,24}\b(?:is|are|was|were|be|been|being|gets?|got)\s+"
        r"(?:sponsored|funded|financed|underwritten)\s+by\b",
        re.IGNORECASE,
    )

    def __init__(self, data_path: Optional[str] = None, config: Optional[C2Config] = None):
        self.c2_v02_config = config or C2Config()
        super().__init__(data_path=data_path, config=self.c2_v02_config)
        self._reference_links: List[ReferenceLink] = []
        self._agentive_relation_items = 0

    def _classify_state(self, text: str):
        state = super()._classify_state(text)
        if (
            state == "asserted"
            and self.config.use_contrastive_corrections
            and self.CONTRASTIVE_CUES.search(text)
        ):
            return "corrective"
        return state

    def _part_split_pattern(self):
        pieces = [self.C2_PART_SPLIT_PATTERN.pattern]
        if self.config.use_structural_revision_boundaries:
            pieces.append(self.REVISION_BOUNDARY)
        if self.config.use_contrastive_corrections:
            pieces.append(self.CONTRAST_BOUNDARY)
        return re.compile("(?:" + "|".join(pieces) + ")", re.IGNORECASE)

    def segment(self, texts: List[str]) -> List[Clause]:
        if not self.config.use_event_identity or not self.config.use_discourse_state:
            return super().segment(texts)

        split_pattern = (
            self._part_split_pattern()
            if self.config.use_sentence_boundaries else self.PART_SPLIT_PATTERN
        )
        clauses = []
        for source_order, raw in enumerate(texts):
            source_id = f"S{source_order + 1:03d}"
            if (
                self.config.use_structural_revision_boundaries
                and re.search(self.REVISION_BOUNDARY, raw, re.IGNORECASE)
            ):
                self._operations.append({
                    "operation": "SPLIT_REVISION_BOUNDARY",
                    "source_id": source_id,
                    "reason": "revision marker after colon",
                })
            if (
                self.config.use_contrastive_corrections
                and re.search(self.CONTRAST_BOUNDARY, raw, re.IGNORECASE)
            ):
                self._operations.append({
                    "operation": "MARK_CONTRASTIVE_CORRECTION",
                    "source_id": source_id,
                    "reason": "standalone correction connective",
                })
            parts = self._clean_parts(split_pattern.split(raw)) if self.config.use_scope else [raw.strip()]
            states = [self._classify_state(part) for part in parts]
            current_scope = "instance:shared"
            for clause_order, (text, state) in enumerate(zip(parts, states)):
                clause_id = f"{source_id}:C{clause_order + 1:03d}"
                if (
                    self.config.use_target_tracking
                    and state not in {"corrective", "provisional", "retracted"}
                    and self._has_event_shift(text)
                ):
                    current_scope = f"instance:{clause_id}"
                    self._operations.append({
                        "operation": "TARGET_SHIFT",
                        "clause_id": clause_id,
                        "target_scope": current_scope,
                        "reason": "typed temporal/event relation",
                    })
                effective_state = state if self.config.use_correction else (
                    "hypothetical" if state == "hypothetical" else "asserted"
                )
                clause = Clause(
                    source_id=source_id,
                    source_order=source_order,
                    clause_id=clause_id,
                    text=text,
                    assertion_status=effective_state,
                    instance_scope=current_scope,
                    discourse_state=effective_state,
                    correction_target=self.config.use_correction and state == "corrective",
                )
                clauses.append(clause)
                if self.config.use_scope:
                    self._operations.append({
                        "operation": "ISOLATE",
                        "clause_id": clause.clause_id,
                        "scope": clause.instance_scope,
                        "reason": "typed sentence/clause boundary",
                    })
                if effective_state != "asserted":
                    self._operations.append({
                        "operation": "STATE_TRANSITION",
                        "clause_id": clause.clause_id,
                        "state": effective_state,
                        "reason": "bounded discourse role",
                    })
        return clauses

    def _apply_context_relations(self, clause, text, ambiguous_matches):
        super()._apply_context_relations(clause, text, ambiguous_matches)
        if not (
            self.config.use_context
            and self.config.use_agentive_affordances
            and ambiguous_matches
        ):
            return

        bank_match = next(
            (match for match in ambiguous_matches if match["item"]["pattern"].lower() == "bank"),
            None,
        )
        if not bank_match:
            return
        trigger_match = self.AGENTIVE_TRIGGER.search(text, bank_match["end"])
        if not trigger_match or trigger_match.start() - bank_match["end"] > 48:
            return
        link_text = text[bank_match["end"]:trigger_match.start()]
        if self.PASSIVE_TAIL.search(link_text):
            return

        trigger = trigger_match.group("trigger").lower()
        negated, depth = self._polarity(
            text, trigger_match.start(), trigger_match.end(), "FINANCIAL_BANK", trigger
        )
        asserted = clause.assertion_status != "hypothetical"
        applied = asserted and not negated
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
                "agentive institutional affordance" if applied else
                "hypothetical agentive affordance" if not asserted else
                "negated agentive affordance"
            ),
        )
        self._relations.append(relation)
        self._agentive_relation_items += 1
        self._operations.append({
            "operation": "INFER_AGENTIVE_AFFORDANCE",
            "relation_id": relation.relation_id,
            "relation_type": relation.relation_type,
            "applied": relation.applied,
            "reason": relation.reason,
        })
        if applied:
            self._append_evidence(
                clause, f"[agentive:{trigger}]", "FINANCIAL_BANK", 1, 0.85,
                "agentive affordance", depth,
            )
            self._append_evidence(
                clause, f"[agentive:{trigger}]", "RIVER_BANK", -1, 0.45,
                "agentive contradiction", depth,
            )

    def _relation_connected(self, text: str, boost_concept: str):
        if (
            boost_concept == "RIVER_BANK"
            and self.config.use_agentive_affordances
            and self.PASSIVE_AGENTIVE_BANK.search(text)
        ):
            return False
        return super()._relation_connected(text, boost_concept)

    def _antecedent_mentions(self, reference_clause: Clause):
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
            if len(mentions) >= 2:
                return clause, mentions
        return None, []

    def _resolve_ordered_references(self):
        if not self.config.use_ordered_coreference:
            return
        for clause in self._clauses:
            match = self.ORDERED_REFERENCE_CUES.search(self.normalize(clause.text))
            if not match:
                continue
            antecedent_clause, mentions = self._antecedent_mentions(clause)
            if not antecedent_clause:
                continue
            cue = (match.group("former_latter") or match.group("ordinal")).lower()
            index = 0 if cue in {"former", "first"} else 1 if cue == "second" else -1
            if index >= len(mentions):
                continue
            antecedent = mentions[index]
            evidence = self._append_evidence(
                clause, f"[reference:{cue}]", antecedent.concept, 1, 1.05,
                "ordered coreference", 0,
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
            self._operations.append({
                "operation": "RESOLVE_REFERENCE",
                "reference_id": link.link_id,
                "clause_id": clause.clause_id,
                "antecedent_clause_id": antecedent_clause.clause_id,
                "antecedent_evidence_id": antecedent.evidence_id,
                "resolution_evidence_id": evidence.evidence_id,
                "cue": cue,
                "concept": antecedent.concept,
            })

    def extract_evidence(self, texts: List[str]):
        self._reference_links = []
        self._agentive_relation_items = 0
        evidence = super().extract_evidence(texts)
        self._resolve_ordered_references()
        self._c1_diagnostics.update({
            "reference_resolutions": len(self._reference_links),
            "agentive_relation_items": self._agentive_relation_items,
            "evidence_items": len(self._ledger),
            "active_evidence_items": sum(item.active for item in self._ledger),
        })
        return evidence

    def _select_domain(self, domain, scores):
        selection = super()._select_domain(domain, scores)
        if not self.config.use_conservative_calibration:
            return selection
        calibrated = dict(selection)
        raw = float(selection.get("selection_confidence", 0.0))
        calibrated["raw_selection_confidence"] = round(raw, 4)
        calibrated["selection_confidence"] = round(
            max(0.70, min(0.93, 0.82 + 0.25 * (raw - 0.82))),
            4,
        )
        calibrated["calibration"] = "shrinkage toward frozen-v0.1 empirical prior"
        return calibrated

    @staticmethod
    def _extend_claim_graph(graph, reference_links):
        if graph.get("invariants", {}).get("disabled"):
            return graph
        nodes = graph["nodes"]
        edges = graph["edges"]
        node_ids = {node["node_id"] for node in nodes}
        for link in reference_links:
            if link["link_id"] not in node_ids:
                nodes.append({
                    "node_id": link["link_id"],
                    "node_type": "REFERENCE",
                    "label": link["cue"],
                    "attributes": {
                        "concept": link["concept"],
                        "antecedent_evidence_id": link["antecedent_evidence_id"],
                    },
                })
                node_ids.add(link["link_id"])
            for source, relation, target in (
                (link["clause_id"], "YIELDS", link["link_id"]),
                (link["link_id"], "RESOLVES_TO", f"CPT:{link['concept']}"),
                (link["link_id"], "REFERS_BACK_TO", link["antecedent_clause_id"]),
            ):
                edges.append({
                    "edge_id": f"G{len(edges) + 1:04d}",
                    "source": source,
                    "relation": relation,
                    "target": target,
                    "attributes": {},
                })
        graph["invariants"] = {
            "unique_node_ids": len(node_ids) == len(nodes),
            "edges_resolve": all(
                edge["source"] in node_ids and edge["target"] in node_ids for edge in edges
            ),
        }
        return graph

    def analyze(self, texts):
        result = super().analyze(texts)
        result["version"] = "PLM-C2 v0.2"
        result["reference_links"] = [asdict(link) for link in self._reference_links]
        result["claim_graph"] = self._extend_claim_graph(
            result["claim_graph"], result["reference_links"]
        )
        result["diagnostics"].update({
            "reference_resolutions": len(self._reference_links),
            "agentive_relation_items": self._agentive_relation_items,
            "claim_graph_nodes": len(result["claim_graph"]["nodes"]),
            "claim_graph_edges": len(result["claim_graph"]["edges"]),
        })
        return result
