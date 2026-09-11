from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
import re

from plm_c1.engine import C1Config as C1V03Config
from plm_c1.engine import Clause, NormalizationEvent, PLMC1Engine as C1V03Engine
from plm_c1.engine import RelationEvidence, ScopedEvidence


@dataclass(frozen=True)
class C2Config(C1V03Config):
    use_typed_claim_graph: bool = True
    use_sentence_boundaries: bool = True
    use_temporal_relations: bool = True
    use_revision_relations: bool = True
    use_irregular_lemmas: bool = True
    use_closed_compounds: bool = True
    use_typed_relation_gate: bool = True


@dataclass
class EventLink:
    link_id: str
    source_event: str
    target_event: str
    relation: str
    same_target: bool


@dataclass
class GraphNode:
    node_id: str
    node_type: str
    label: str
    attributes: Dict


@dataclass
class GraphEdge:
    edge_id: str
    source: str
    relation: str
    target: str
    attributes: Dict


class PLMC2Engine(C1V03Engine):
    """PLM-C2 v0.1: typed claims, relations, events, and Concept grounding."""

    C2_PART_SPLIT_PATTERN = re.compile(
        r"(?:[。！？!?;]+|、|—+|(?<!\d)\.(?!\d)|\bwhile\b|\bbut\b)",
        re.IGNORECASE,
    )
    TEMPORAL_SHIFT_CUES = re.compile(
        r"(?:\bsubsequently\b|\bthereafter\b|\bnext\b|\bfollowing\s+that\b|"
        r"\bin\s+the\s+next\s+(?:case|instance|event)\b|続いて|次いで|以後)",
        re.IGNORECASE,
    )
    C2_PROVISIONAL_CUES = re.compile(
        r"(?:\boriginally\b|\bat\s+the\s+outset\b|\bearlier\s+finding\b|"
        r"当初の判定|元の判定|初期判断)",
        re.IGNORECASE,
    )
    C2_CORRECTIVE_CUES = re.compile(
        r"(?:\brevised\b|\bamended\b|\bupdated\s+finding\b|\bcorrected\s+result\b|"
        r"改訂|修正版|再判定|更新結果)",
        re.IGNORECASE,
    )
    IRREGULAR_FORMS = {
        "bite": ("bitten",),
    }
    CLOSED_COMPOUNDS = {
        "river": ("bank", "banks"),
    }

    def __init__(self, data_path: Optional[str] = None, config: Optional[C2Config] = None):
        self.c2_config = config or C2Config()
        super().__init__(data_path=data_path, config=self.c2_config)
        self._event_links: List[EventLink] = []
        self._relation_gated_evidence = 0

    def _classify_state(self, text: str):
        state = super()._classify_state(text)
        if state != "asserted" or not self.config.use_revision_relations:
            return state
        if self.C2_CORRECTIVE_CUES.search(text):
            return "corrective"
        if self.C2_PROVISIONAL_CUES.search(text):
            return "provisional"
        return "asserted"

    def _has_event_shift(self, text: str):
        if self.EVENT_SHIFT_CUES.search(text):
            return True
        return self.config.use_temporal_relations and bool(self.TEMPORAL_SHIFT_CUES.search(text))

    def segment(self, texts: List[str]) -> List[Clause]:
        if not self.config.use_event_identity or not self.config.use_discourse_state:
            return super().segment(texts)

        split_pattern = (
            self.C2_PART_SPLIT_PATTERN
            if self.config.use_sentence_boundaries else self.PART_SPLIT_PATTERN
        )
        clauses = []
        for source_order, raw in enumerate(texts):
            source_id = f"S{source_order + 1:03d}"
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
                        "reason": "typed discourse revision role",
                    })
        return clauses

    def _compound_suffixes(self, pattern: str):
        suffixes = list(C1V03Engine.APPROVED_COMPOUNDS.get(pattern, ()))
        if self.config.use_closed_compounds:
            suffixes.extend(self.CLOSED_COMPOUNDS.get(pattern, ()))
        return tuple(dict.fromkeys(suffixes))

    def _pattern_regex(self, pattern: str) -> str:
        if not (
            pattern.isascii()
            and pattern.isalpha()
            and self.config.use_morphology
            and self.config.use_lemma_normalization
        ):
            return super()._pattern_regex(pattern)

        variants = [self._inflected_ascii_pattern(pattern)]
        if self.config.use_irregular_lemmas:
            variants.extend(re.escape(value) for value in self.IRREGULAR_FORMS.get(pattern, ()))
        if self.config.use_compound_analysis:
            variants.extend(
                re.escape(pattern.lower() + suffix)
                for suffix in self._compound_suffixes(pattern)
            )
        core = "(?:" + "|".join(variants) + ")"
        if self.config.strict_ascii_boundaries:
            return rf"(?<![A-Za-z0-9_]){core}(?![A-Za-z0-9_])"
        return core

    def _record_normalizations(self, clause: Clause, evidence_start: int):
        text = self.normalize(clause.text)
        seen = set()
        for evidence in self._ledger[evidence_start:]:
            pattern = evidence.pattern
            if (
                evidence.reason not in {"direct lexical support", "ambiguous lexical candidate"}
                or not pattern.isascii() or not pattern.isalpha()
            ):
                continue
            for match in self._find_matches(text, pattern):
                surface = match.group(0).lower()
                if surface == pattern.lower() or (pattern, surface) in seen:
                    continue
                seen.add((pattern, surface))
                if surface in self.IRREGULAR_FORMS.get(pattern, ()):
                    method = "irregular_lemma"
                    operation = "NORMALIZE_IRREGULAR"
                elif any(surface == pattern + suffix for suffix in self._compound_suffixes(pattern)):
                    method = "closed_compound" if surface in {
                        pattern + suffix for suffix in self.CLOSED_COMPOUNDS.get(pattern, ())
                    } else "approved_compound"
                    operation = "SEGMENT_COMPOUND"
                else:
                    method = "inflection"
                    operation = "NORMALIZE_MORPHOLOGY"
                event = NormalizationEvent(
                    normalization_id=f"N{len(self._normalizations) + 1:04d}",
                    clause_id=clause.clause_id,
                    surface=surface,
                    lemma=pattern.lower(),
                    method=method,
                )
                self._normalizations.append(event)
                self._operations.append({
                    "operation": operation,
                    "normalization_id": event.normalization_id,
                    "clause_id": clause.clause_id,
                    "surface": surface,
                    "lemma": pattern.lower(),
                    "method": method,
                })

    def _gate_untyped_relation_evidence(self, clause: Clause, evidence_start: int):
        if not self.config.use_typed_relation_gate:
            return
        clause_evidence = self._ledger[evidence_start:]
        has_ambiguous_bank = any(
            evidence.pattern == "bank" and evidence.reason == "ambiguous lexical candidate"
            for evidence in clause_evidence
        )
        if not has_ambiguous_bank:
            return
        spatial_relation_applied = any(
            relation.clause_id == clause.clause_id
            and relation.relation_type == "SPATIAL_ASSOCIATION"
            and relation.applied
            for relation in self._relations
        )
        if spatial_relation_applied:
            return
        for evidence in clause_evidence:
            if (
                evidence.active
                and evidence.concept == "RIVER_BANK"
                and evidence.pattern == "river"
                and evidence.reason == "direct lexical support"
            ):
                evidence.active = False
                evidence.effective_weight = 0.0
                evidence.assertion_status = "relation_gated"
                self._relation_gated_evidence += 1
                self._operations.append({
                    "operation": "RELATION_GATE",
                    "evidence_id": evidence.evidence_id,
                    "concept": evidence.concept,
                    "clause_id": clause.clause_id,
                    "reason": "river mention lacks a spatial bank-of relation",
                })

    def _extract_clause(self, clause: Clause):
        evidence_start = len(self._ledger)
        counts = super()._extract_clause(clause)
        self._gate_untyped_relation_evidence(clause, evidence_start)
        return counts

    def _build_event_links(self, clauses):
        if not self.config.use_temporal_relations:
            return []
        links = []
        for previous, current in zip(clauses, clauses[1:]):
            same_target = previous["instance_scope"] == current["instance_scope"]
            relation = "SAME_TARGET_SEQUENCE" if same_target else "NEXT_DISTINCT_TARGET"
            links.append(EventLink(
                link_id=f"L{len(links) + 1:04d}",
                source_event=f"EV:{previous['clause_id']}",
                target_event=f"EV:{current['clause_id']}",
                relation=relation,
                same_target=same_target,
            ))
        return links

    @staticmethod
    def _graph_add_edge(edges, source, relation, target, attributes=None):
        edges.append(GraphEdge(
            edge_id=f"G{len(edges) + 1:04d}",
            source=source,
            relation=relation,
            target=target,
            attributes=attributes or {},
        ))

    def _build_claim_graph(self, result):
        if not self.config.use_typed_claim_graph:
            return {"schema_version": 1, "nodes": [], "edges": [], "invariants": {"disabled": True}}
        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []

        def add_node(node_id, node_type, label, attributes=None):
            nodes.setdefault(node_id, GraphNode(node_id, node_type, label, attributes or {}))

        for index, text in enumerate(result["inputs"], start=1):
            source_id = f"S{index:03d}"
            add_node(source_id, "SOURCE", source_id, {"text": text})
        for concept_id, concept in sorted(self.concepts.items()):
            add_node(
                f"CPT:{concept_id}", "CONCEPT", concept_id,
                {"domain": concept["domain"], "label_ja": concept["label_ja"]},
            )
        for clause in result["clauses"]:
            clause_id = clause["clause_id"]
            event_id = f"EV:{clause_id}"
            add_node(clause_id, "CLAUSE", clause_id, {
                "text": clause["text"], "discourse_state": clause["discourse_state"],
            })
            add_node(event_id, "EVENT", event_id, {
                "instance_scope": clause["instance_scope"],
                "discourse_state": clause["discourse_state"],
            })
            self._graph_add_edge(edges, clause["source_id"], "CONTAINS", clause_id)
            self._graph_add_edge(edges, clause_id, "DESCRIBES", event_id)
        for target_id, summary in result["targets"].items():
            add_node(target_id, "ENTITY", target_id, summary)
        for evidence in result["evidence"]:
            evidence_id = evidence["evidence_id"]
            add_node(evidence_id, "EVIDENCE", evidence["pattern"], {
                "vote": evidence["vote"], "weight": evidence["effective_weight"],
                "active": evidence["active"], "status": evidence["assertion_status"],
            })
            self._graph_add_edge(edges, evidence["clause_id"], "YIELDS", evidence_id)
            self._graph_add_edge(
                edges, evidence_id,
                "SUPPORTS" if evidence["vote"] > 0 else "CONTRADICTS",
                f"CPT:{evidence['concept']}",
            )
            self._graph_add_edge(edges, evidence_id, "ABOUT", evidence["target_id"])
            self._graph_add_edge(edges, f"EV:{evidence['clause_id']}", "ABOUT", evidence["target_id"])
        relation_concepts = {
            "FINANCIAL_AFFORDANCE": "FINANCIAL_BANK",
            "SPATIAL_ASSOCIATION": "RIVER_BANK",
        }
        for relation in result["relations"]:
            relation_id = relation["relation_id"]
            add_node(relation_id, "RELATION", relation["relation_type"], {
                "applied": relation["applied"], "polarity": relation["polarity"],
                "reason": relation["reason"],
            })
            self._graph_add_edge(edges, relation["clause_id"], "YIELDS", relation_id)
            self._graph_add_edge(edges, relation_id, "ABOUT", relation["target_id"])
            concept = relation_concepts.get(relation["relation_type"])
            if concept:
                self._graph_add_edge(
                    edges, relation_id, "GROUNDS" if relation["applied"] else "DOES_NOT_GROUND",
                    f"CPT:{concept}",
                )
        for link in self._event_links:
            self._graph_add_edge(
                edges, link.source_event, link.relation, link.target_event,
                {"same_target": link.same_target},
            )
        for operation in result["operations"]:
            if operation["operation"] == "SUPERSEDE":
                self._graph_add_edge(
                    edges, operation["replacement_evidence_id"], "SUPERSEDES",
                    operation["evidence_id"],
                )

        node_ids = set(nodes)
        edges_resolve = all(edge.source in node_ids and edge.target in node_ids for edge in edges)
        return {
            "schema_version": 1,
            "nodes": [asdict(nodes[node_id]) for node_id in sorted(nodes)],
            "edges": [asdict(edge) for edge in edges],
            "invariants": {
                "unique_node_ids": len(node_ids) == len(nodes),
                "edges_resolve": edges_resolve,
            },
        }

    def extract_evidence(self, texts: List[str]):
        self._relation_gated_evidence = 0
        evidence = super().extract_evidence(texts)
        self._c1_diagnostics.update({
            "relation_gated_evidence": self._relation_gated_evidence,
            "irregular_lemma_events": sum(
                event.method == "irregular_lemma" for event in self._normalizations
            ),
            "closed_compound_events": sum(
                event.method == "closed_compound" for event in self._normalizations
            ),
        })
        return evidence

    def analyze(self, texts):
        result = super().analyze(texts)
        self._event_links = self._build_event_links(result["clauses"])
        result["version"] = "PLM-C2 v0.1"
        result["event_links"] = [asdict(link) for link in self._event_links]
        result["claim_graph"] = self._build_claim_graph(result)
        result["diagnostics"].update({
            "event_links": len(self._event_links),
            "claim_graph_nodes": len(result["claim_graph"]["nodes"]),
            "claim_graph_edges": len(result["claim_graph"]["edges"]),
            "relation_gated_evidence": self._relation_gated_evidence,
            "irregular_lemma_events": sum(
                event.method == "irregular_lemma" for event in self._normalizations
            ),
            "closed_compound_events": sum(
                event.method == "closed_compound" for event in self._normalizations
            ),
        })
        return result
