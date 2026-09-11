from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
import re

from plm_c1_v01.engine import C1Config as V01Config
from plm_c1_v01.engine import PLMC1Engine as V01Engine


@dataclass(frozen=True)
class C1Config(V01Config):
    use_polarity_composition: bool = True
    use_discourse_state: bool = True
    use_morphology: bool = True
    use_target_tracking: bool = True
    use_relation_context: bool = True


@dataclass
class Clause:
    source_id: str
    source_order: int
    clause_id: str
    text: str
    assertion_status: str
    instance_scope: str
    discourse_state: str
    correction_target: bool = False


@dataclass
class ScopedEvidence:
    evidence_id: str
    text_index: int
    source_id: str
    source_order: int
    clause_id: str
    scope: str
    target_id: str
    source_text: str
    pattern: str
    concept: str
    vote: int
    polarity_depth: int
    weight: float
    effective_weight: float
    reason: str
    assertion_status: str
    active: bool = True
    superseded_by: Optional[str] = None


@dataclass
class RelationEvidence:
    relation_id: str
    clause_id: str
    target_id: str
    relation_type: str
    ambiguous_pattern: str
    trigger: str
    polarity: int
    assertion_status: str
    applied: bool
    reason: str


class PLMC1Engine(V01Engine):
    """PLM-C1 v0.2: compositional polarity and discourse-state prototype."""

    PART_SPLIT_PATTERN = re.compile(
        r"(?:[。！？!?;]+|、|—+|\bwhile\b|\bbut\b)",
        re.IGNORECASE,
    )
    PROVISIONAL_CUES = re.compile(
        r"(?:\binitially\b|\bat\s+first\b|\bseemed\b|\blooked\s+like\b|"
        r"\bthought\b|当初|最初|と思った|らしい)",
        re.IGNORECASE,
    )
    CORRECTIVE_CUES = re.compile(
        r"(?:\bactually\b|\bhowever\b|\bupdate\b|\bconfirmed\b|\bfinal\b|"
        r"\bin\s+fact\b|実際|訂正|正しく|いや|判明)",
        re.IGNORECASE,
    )
    HYPOTHETICAL_CUES = re.compile(r"(?:\bif\b|\bwould\b|もし|仮に)", re.IGNORECASE)
    INSTANCE_SHIFT_CUES = re.compile(
        r"(?:\bseparately\b|\blater\b|\bafterward\b|その後|別(?:に|の))",
        re.IGNORECASE,
    )
    ENGLISH_NEGATORS = re.compile(
        r"\b(?:not|no|never|without|nowhere|denied|deny|denies|impossible)\b",
        re.IGNORECASE,
    )
    JAPANESE_NEGATORS = re.compile(r"(?:なかった|ではない|じゃない|でない|ない|なく|ません|ぬ)")
    SPATIAL_RELATION_CUES = re.compile(
        r"(?:\bbeside\b|\bnear\b|\bnearby\b|\balong\b|\bby\b|"
        r"\bclose\s+to\b|\bfollows?\b|そば|近く|沿い|流れ)",
        re.IGNORECASE,
    )

    def __init__(self, data_path: Optional[str] = None, config: Optional[C1Config] = None):
        self.v02_config = config or C1Config()
        super().__init__(data_path=data_path, config=self.v02_config)
        self._relations: List[RelationEvidence] = []

    def _pattern_regex(self, pattern: str) -> str:
        escaped = re.escape(pattern.lower())
        if pattern.isascii() and pattern.isalpha() and self.config.use_morphology and not pattern.endswith("s"):
            escaped = rf"{escaped}(?:s|es)?"
        if self.config.strict_ascii_boundaries and pattern.isascii() and any(char.isalnum() for char in pattern):
            return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
        return escaped

    @staticmethod
    def _clean_parts(parts):
        return [part.strip(" ,、\t\r\n") for part in parts if part.strip(" ,、\t\r\n")]

    def _classify_state(self, text: str):
        if self.HYPOTHETICAL_CUES.search(text):
            return "hypothetical"
        if self.CORRECTIVE_CUES.search(text):
            return "corrective"
        if self.PROVISIONAL_CUES.search(text):
            return "provisional"
        return "asserted"

    def _legacy_segment(self, texts: List[str]):
        clauses = []
        for source_order, raw in enumerate(texts):
            source_id = f"S{source_order + 1:03d}"
            isolated = bool(V01Engine.ISOLATION_PATTERN.search(raw)) if self.config.use_scope else False
            instance_scope = f"instance:{source_id}" if isolated else "instance:shared"
            correction_match = (
                V01Engine.CORRECTION_PATTERN.search(raw)
                if self.config.use_correction else None
            )
            sections = []
            if correction_match:
                before = raw[:correction_match.start()]
                after = raw[correction_match.end():]
                sections.extend((piece, "provisional", False) for piece in self._split_scope(before))
                sections.extend((piece, "corrective", True) for piece in self._split_scope(after))
            else:
                sections.extend((piece, "asserted", False) for piece in self._split_scope(raw))
            for clause_order, (text, status, correction_target) in enumerate(sections):
                clause = Clause(
                    source_id, source_order, f"{source_id}:C{clause_order + 1:03d}",
                    text, status, instance_scope, "legacy", correction_target,
                )
                clauses.append(clause)
                if self.config.use_scope:
                    self._operations.append({
                        "operation": "ISOLATE",
                        "clause_id": clause.clause_id,
                        "scope": clause.instance_scope,
                        "reason": "legacy clause-local evidence and context",
                    })
        return clauses

    def segment(self, texts: List[str]) -> List[Clause]:
        if not self.config.use_discourse_state:
            return self._legacy_segment(texts)
        clauses = []
        for source_order, raw in enumerate(texts):
            source_id = f"S{source_order + 1:03d}"
            parts = (
                self._clean_parts(self.PART_SPLIT_PATTERN.split(raw))
                if self.config.use_scope else [raw.strip()]
            )
            states = [self._classify_state(part) for part in parts]
            has_correction = self.config.use_correction and "corrective" in states
            isolated = (
                self.config.use_target_tracking
                and bool(self.INSTANCE_SHIFT_CUES.search(raw))
                and not has_correction
            )
            instance_scope = f"instance:{source_id}" if isolated else "instance:shared"
            for clause_order, (text, state) in enumerate(zip(parts, states)):
                effective_state = state if self.config.use_correction else (
                    "hypothetical" if state == "hypothetical" else "asserted"
                )
                correction_target = self.config.use_correction and state == "corrective"
                clause = Clause(
                    source_id=source_id,
                    source_order=source_order,
                    clause_id=f"{source_id}:C{clause_order + 1:03d}",
                    text=text,
                    assertion_status=effective_state,
                    instance_scope=instance_scope,
                    discourse_state=effective_state,
                    correction_target=correction_target,
                )
                clauses.append(clause)
                if self.config.use_scope:
                    self._operations.append({
                        "operation": "ISOLATE",
                        "clause_id": clause.clause_id,
                        "scope": clause.instance_scope,
                        "reason": "discourse clause boundary",
                    })
                if effective_state != "asserted":
                    self._operations.append({
                        "operation": "STATE_TRANSITION",
                        "clause_id": clause.clause_id,
                        "state": effective_state,
                        "reason": "discourse cue classification",
                    })
        return clauses

    def _polarity(self, text: str, start: int, end: int, concept: str, pattern: str):
        if not self.config.use_negation:
            return False, 0
        if not self.config.use_polarity_composition:
            negated = V01Engine._scoped_negated(self, text, start, end, concept, pattern)
            return negated, int(negated)
        if concept == "FINANCIAL_BANK" and pattern.lower() in self.FINANCIAL_FEATURES:
            return False, 0

        tail = text[end:min(len(text), end + 42)]
        japanese_depth = len(self.JAPANESE_NEGATORS.findall(tail))
        before = text[:start]
        adversatives = list(re.finditer(r"(?:\bbut\b|\bhowever\b|\byet\b|しかし|けれど|だが|いや)", before))
        if adversatives:
            before = before[adversatives[-1].end():]
        before = re.sub(r"\bnot\s+only\b", "", before, flags=re.IGNORECASE)
        english_depth = len(self.ENGLISH_NEGATORS.findall(before))
        depth = japanese_depth + english_depth
        return bool(depth % 2), depth

    def _scoped_negated(self, text: str, start: int, end: int, concept: str, pattern: str):
        return self._polarity(text, start, end, concept, pattern)[0]

    def _target_id(self, clause: Clause, concept: str):
        domain = self.concepts[concept]["domain"]
        if not self.config.use_target_tracking:
            return f"T:shared:{domain}"
        instance = clause.instance_scope.split(":", 1)[1]
        return f"T:{instance}:{domain}"

    def _append_evidence(
        self,
        clause: Clause,
        pattern: str,
        concept: str,
        vote: int,
        weight: float,
        reason: str,
        polarity_depth: int = 0,
    ):
        multiplier = 0.25 if clause.assertion_status == "hypothetical" else 1.0
        evidence = ScopedEvidence(
            evidence_id=f"E{len(self._ledger) + 1:04d}",
            text_index=clause.source_order,
            source_id=clause.source_id,
            source_order=clause.source_order,
            clause_id=clause.clause_id,
            scope=f"{clause.instance_scope}/{clause.clause_id}",
            target_id=self._target_id(clause, concept),
            source_text=clause.text,
            pattern=pattern,
            concept=concept,
            vote=vote,
            polarity_depth=polarity_depth,
            weight=float(weight),
            effective_weight=float(weight) * multiplier,
            reason=reason,
            assertion_status=clause.assertion_status,
        )
        self._ledger.append(evidence)
        if vote < 0:
            self._operations.append({
                "operation": "NEGATE",
                "evidence_id": evidence.evidence_id,
                "concept": concept,
                "clause_id": clause.clause_id,
                "polarity_depth": polarity_depth,
                "amount": evidence.effective_weight,
                "reason": reason,
            })
        elif polarity_depth >= 2:
            self._operations.append({
                "operation": "POLARITY_COMPOSE",
                "evidence_id": evidence.evidence_id,
                "concept": concept,
                "polarity_depth": polarity_depth,
                "resulting_vote": vote,
            })
        return evidence

    def _relation_type(self, boost_concept: str):
        return "FINANCIAL_AFFORDANCE" if boost_concept == "FINANCIAL_BANK" else "SPATIAL_ASSOCIATION"

    def _relation_connected(self, text: str, boost_concept: str):
        if not self.config.use_relation_context:
            return True
        if boost_concept == "FINANCIAL_BANK":
            return True
        return bool(self.SPATIAL_RELATION_CUES.search(text))

    def _apply_context_relations(self, clause: Clause, text: str, ambiguous_matches):
        if not self.config.use_context or not ambiguous_matches:
            return
        ambiguous_pattern = ambiguous_matches[0]["item"]["pattern"]
        for rule in self.data.get("context_rules", []):
            boost_concept = next(iter(rule.get("boost", {})), "")
            trigger_match = None
            trigger_text = None
            for trigger in rule["trigger"]:
                match = next(self._find_matches(text, trigger), None)
                if match:
                    trigger_match = match
                    trigger_text = trigger
                    break
            if not trigger_match:
                continue
            negated, depth = self._polarity(
                text, trigger_match.start(), trigger_match.end(), boost_concept, trigger_text
            )
            polarity = -1 if negated else 1
            connected = self._relation_connected(text, boost_concept)
            asserted = clause.assertion_status != "hypothetical"
            polarity_allowed = not (negated and rule.get("negation_sensitive", True))
            applied = connected and asserted and polarity_allowed
            relation = RelationEvidence(
                relation_id=f"R{len(self._relations) + 1:04d}",
                clause_id=clause.clause_id,
                target_id=self._target_id(clause, boost_concept),
                relation_type=self._relation_type(boost_concept),
                ambiguous_pattern=ambiguous_pattern,
                trigger=trigger_text,
                polarity=polarity,
                assertion_status=clause.assertion_status,
                applied=applied,
                reason=(
                    "relation accepted" if applied else
                    "hypothetical relation" if not asserted else
                    "negated relation" if not polarity_allowed else
                    "no supported relation between ambiguous term and trigger"
                ),
            )
            self._relations.append(relation)
            self._operations.append({
                "operation": "RELATE",
                "relation_id": relation.relation_id,
                "relation_type": relation.relation_type,
                "applied": applied,
                "reason": relation.reason,
            })
            if not applied:
                continue
            for concept, weight in rule.get("boost", {}).items():
                self._append_evidence(
                    clause, f"[relation:{trigger_text}]", concept, 1, weight,
                    "context boost", depth,
                )
            for concept, weight in rule.get("suppress", {}).items():
                self._append_evidence(
                    clause, f"[relation:{trigger_text}]", concept, -1, weight,
                    "context contradiction", depth,
                )

    def _extract_clause(self, clause: Clause):
        text = self.normalize(clause.text)
        raw_match_count = 0
        for item in self.data["lexicon"]:
            raw_match_count += sum(1 for _ in self._find_matches(text, item["pattern"]))
        for item in self.data.get("ambiguous_lexicon", []):
            raw_match_count += sum(1 for _ in self._find_matches(text, item["pattern"]))
        matches = self._surface_matches(text)

        for match in matches:
            item = match["item"]
            if match["kind"] == "lexicon":
                concepts = [(item["concept"], float(item["weight"]))]
            else:
                concepts = [
                    (candidate["concept"], float(candidate["weight"]))
                    for candidate in item["candidates"]
                ]
            for concept, weight in concepts:
                negated, depth = self._polarity(
                    text, match["start"], match["end"], concept, item["pattern"]
                )
                if negated:
                    reason = "composed polarity negation"
                elif match["kind"] == "ambiguous":
                    reason = "ambiguous lexical candidate"
                else:
                    reason = "direct lexical support"
                self._append_evidence(
                    clause, item["pattern"], concept, -1 if negated else 1,
                    weight, reason, depth,
                )

        ambiguous_matches = [match for match in matches if match["kind"] == "ambiguous"]
        self._apply_context_relations(clause, text, ambiguous_matches)
        return raw_match_count, len(matches)

    def _detect_isolated_instance_conflicts(self):
        if not self.config.use_target_tracking:
            return
        targets_by_domain = {}
        for evidence in self._ledger:
            if not evidence.active or evidence.vote <= 0:
                continue
            domain = self.concepts[evidence.concept]["domain"]
            targets_by_domain.setdefault(domain, set()).add(evidence.target_id)
        for domain, target_ids in targets_by_domain.items():
            if len(target_ids) > 1:
                self._forced_unresolved_domains.add(domain)
                self._operations.append({
                    "operation": "ISOLATE_CONFLICT",
                    "domain": domain,
                    "target_ids": sorted(target_ids),
                    "reason": "multiple target instances cannot share one Concept selection",
                })

    def extract_evidence(self, texts: List[str]):
        self._relations = []
        evidence = super().extract_evidence(texts)
        self._c1_diagnostics.update({
            "relation_items": len(self._relations),
            "applied_relation_items": sum(relation.applied for relation in self._relations),
            "target_ids": len({item.target_id for item in self._ledger}),
        })
        return evidence

    def _target_summary(self):
        targets: Dict[str, Dict] = {}
        for evidence in self._ledger:
            target = targets.setdefault(evidence.target_id, {
                "concepts": set(),
                "source_ids": set(),
                "active_evidence_items": 0,
            })
            target["concepts"].add(evidence.concept)
            target["source_ids"].add(evidence.source_id)
            target["active_evidence_items"] += int(evidence.active)
        return {
            target_id: {
                "concepts": sorted(values["concepts"]),
                "source_ids": sorted(values["source_ids"]),
                "active_evidence_items": values["active_evidence_items"],
            }
            for target_id, values in sorted(targets.items())
        }

    def analyze(self, texts):
        result = super().analyze(texts)
        result["version"] = "PLM-C1 v0.2"
        result["relations"] = [asdict(relation) for relation in self._relations]
        result["targets"] = self._target_summary()
        result["diagnostics"].update({
            "relation_items": len(self._relations),
            "applied_relation_items": sum(relation.applied for relation in self._relations),
            "target_ids": len(result["targets"]),
        })
        return result
