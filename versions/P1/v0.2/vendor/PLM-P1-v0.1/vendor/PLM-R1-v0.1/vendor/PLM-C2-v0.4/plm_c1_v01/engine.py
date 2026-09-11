from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional
import re

from plm_c0.engine import ConceptScore, PLMC0Engine


@dataclass(frozen=True)
class C1Config:
    use_negation: bool = True
    use_context: bool = True
    use_hierarchy: bool = True
    use_sibling_contradiction: bool = True
    suppress_overlaps: bool = True
    strict_ascii_boundaries: bool = True
    use_scope: bool = True
    use_correction: bool = True
    use_residual: bool = True


@dataclass
class Clause:
    source_id: str
    source_order: int
    clause_id: str
    text: str
    assertion_status: str
    instance_scope: str
    correction_target: bool = False


@dataclass
class ScopedEvidence:
    evidence_id: str
    text_index: int
    source_id: str
    source_order: int
    clause_id: str
    scope: str
    source_text: str
    pattern: str
    concept: str
    vote: int
    weight: float
    effective_weight: float
    reason: str
    assertion_status: str
    active: bool = True
    superseded_by: Optional[str] = None


class PLMC1Engine(PLMC0Engine):
    """PLM-C1 v0.1: scoped evidence with explicit residual operations."""

    CORRECTION_PATTERN = re.compile(
        r"(?:、?\s*実際は|訂正すると|正しくは|"
        r"\bbut\s+the\s+final\s+identification\s+was\b|"
        r"\bbut\s+actually\b|\bcorrection\s*:)",
        re.IGNORECASE,
    )
    SCOPE_SPLIT_PATTERN = re.compile(r"(?:[。！？!?;]+|\bwhile\b)", re.IGNORECASE)
    ISOLATION_PATTERN = re.compile(r"(?:\bseparately\b|\blater\b|別(?:に|の))", re.IGNORECASE)
    FINANCIAL_FEATURES = {"loan", "loans", "account", "deposit", "money", "預金", "口座"}

    def __init__(self, data_path: Optional[str] = None, config: Optional[C1Config] = None):
        self.c1_config = config or C1Config()
        data_path = data_path or (Path(__file__).resolve().parents[1] / "data" / "concepts_c1.json")
        super().__init__(data_path=data_path, config=self.c1_config)
        self._clauses: List[Clause] = []
        self._ledger: List[ScopedEvidence] = []
        self._operations: List[Dict] = []
        self._forced_unresolved_domains = set()
        self._c1_diagnostics: Dict[str, int] = {}

    def _pattern_regex(self, pattern: str) -> str:
        escaped = re.escape(pattern.lower())
        if self.config.strict_ascii_boundaries and pattern.isascii() and any(char.isalnum() for char in pattern):
            return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
        return escaped

    @staticmethod
    def _nonempty(parts):
        return [part.strip(" ,、\t\r\n") for part in parts if part.strip(" ,、\t\r\n")]

    def _split_scope(self, text: str):
        if not self.c1_config.use_scope:
            return [text.strip()] if text.strip() else []
        return self._nonempty(self.SCOPE_SPLIT_PATTERN.split(text))

    def segment(self, texts: List[str]) -> List[Clause]:
        clauses = []
        for source_order, raw in enumerate(texts):
            source_id = f"S{source_order + 1:03d}"
            isolated = bool(self.ISOLATION_PATTERN.search(raw)) if self.c1_config.use_scope else False
            instance_scope = f"instance:{source_id}" if isolated else "instance:shared"
            correction_match = (
                self.CORRECTION_PATTERN.search(raw)
                if self.c1_config.use_correction else None
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
                    source_id=source_id,
                    source_order=source_order,
                    clause_id=f"{source_id}:C{clause_order + 1:03d}",
                    text=text,
                    assertion_status=status,
                    instance_scope=instance_scope,
                    correction_target=correction_target,
                )
                clauses.append(clause)
                if self.c1_config.use_scope:
                    self._operations.append({
                        "operation": "ISOLATE",
                        "clause_id": clause.clause_id,
                        "scope": clause.instance_scope,
                        "reason": "clause-local evidence and context",
                    })
        return clauses

    @staticmethod
    def _tail_is_japanese_negation(tail: str) -> bool:
        return bool(re.match(
            r"(?:というわけ)?(?:では|じゃ|で)?(?:ない|なく|なかった)|"
            r"(?:なかった|ない|ません)",
            tail,
        ))

    def _scoped_negated(
        self,
        text: str,
        start: int,
        end: int,
        concept: str,
        pattern: str,
    ) -> bool:
        if not self.c1_config.use_negation:
            return False
        if concept == "FINANCIAL_BANK" and pattern.lower() in self.FINANCIAL_FEATURES:
            return False
        tail = text[end:min(len(text), end + 30)]
        if self._tail_is_japanese_negation(tail):
            return True
        before = text[:start]
        adversatives = list(re.finditer(r"(?:\bbut\b|\bhowever\b|\byet\b|しかし|けれど|だが)", before))
        if adversatives:
            before = before[adversatives[-1].end():]
        if re.search(r"\bnot\s+only\b", before):
            before = re.sub(r"\bnot\s+only\b", "", before)
        return bool(re.search(r"\b(?:not|no|never|without)\b", before))

    def _append_evidence(
        self,
        clause: Clause,
        pattern: str,
        concept: str,
        vote: int,
        weight: float,
        reason: str,
    ):
        evidence = ScopedEvidence(
            evidence_id=f"E{len(self._ledger) + 1:04d}",
            text_index=clause.source_order,
            source_id=clause.source_id,
            source_order=clause.source_order,
            clause_id=clause.clause_id,
            scope=f"{clause.instance_scope}/{clause.clause_id}",
            source_text=clause.text,
            pattern=pattern,
            concept=concept,
            vote=vote,
            weight=float(weight),
            effective_weight=float(weight),
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
                "amount": float(weight),
                "reason": reason,
            })
        return evidence

    def _extract_clause(self, clause: Clause):
        text = self.normalize(clause.text)
        raw_match_count = 0
        for item in self.data["lexicon"]:
            raw_match_count += sum(1 for _ in self._find_matches(text, item["pattern"]))
        for item in self.data.get("ambiguous_lexicon", []):
            raw_match_count += sum(1 for _ in self._find_matches(text, item["pattern"]))
        matches = self._surface_matches(text)
        ambiguous_present = any(match["kind"] == "ambiguous" for match in matches)

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
                negated = self._scoped_negated(
                    text, match["start"], match["end"], concept, item["pattern"]
                )
                if negated:
                    reason = (
                        "scoped ambiguous negation"
                        if match["kind"] == "ambiguous" else "scoped negation"
                    )
                else:
                    reason = (
                        "ambiguous lexical candidate"
                        if match["kind"] == "ambiguous" else "direct lexical support"
                    )
                self._append_evidence(
                    clause, item["pattern"], concept, -1 if negated else 1, weight, reason
                )

        if self.c1_config.use_context and (ambiguous_present or not self.c1_config.use_scope):
            for rule in self.data.get("context_rules", []):
                valid_trigger = None
                boost_concept = next(iter(rule.get("boost", {})), "")
                for trigger in rule["trigger"]:
                    for match in self._find_matches(text, trigger):
                        trigger_negated = self._scoped_negated(
                            text, match.start(), match.end(), boost_concept, trigger
                        )
                        if trigger_negated and rule.get("negation_sensitive", True):
                            continue
                        valid_trigger = trigger
                        break
                    if valid_trigger:
                        break
                if valid_trigger:
                    for concept, weight in rule.get("boost", {}).items():
                        self._append_evidence(
                            clause, f"[context:{valid_trigger}]", concept, 1, weight,
                            "context boost",
                        )
                    for concept, weight in rule.get("suppress", {}).items():
                        self._append_evidence(
                            clause, f"[context:{valid_trigger}]", concept, -1, weight,
                            "context contradiction",
                        )
        return raw_match_count, len(matches)

    def _apply_corrections(self):
        corrective_clauses = [clause for clause in self._clauses if clause.correction_target]
        for clause in corrective_clauses:
            replacements = [
                evidence for evidence in self._ledger
                if evidence.clause_id == clause.clause_id
                and evidence.vote > 0
                and evidence.reason in {"direct lexical support", "ambiguous lexical candidate"}
            ]
            replacement_by_domain = {}
            for evidence in replacements:
                domain = self.concepts[evidence.concept]["domain"]
                replacement_by_domain.setdefault(domain, evidence)
            for domain, replacement in replacement_by_domain.items():
                targets = [
                    evidence for evidence in self._ledger
                    if evidence.active
                    and evidence.vote > 0
                    and self.concepts[evidence.concept]["domain"] == domain
                    and evidence.concept != replacement.concept
                    and (
                        evidence.source_order < clause.source_order
                        or (
                            evidence.source_order == clause.source_order
                            and evidence.clause_id < clause.clause_id
                        )
                    )
                ]
                for target in targets:
                    operation = {
                        "operation": "SUPERSEDE" if self.c1_config.use_residual else "SUPERSEDE_SKIPPED",
                        "evidence_id": target.evidence_id,
                        "concept": target.concept,
                        "replacement_evidence_id": replacement.evidence_id,
                        "replacement_concept": replacement.concept,
                        "residual_removed": target.effective_weight if self.c1_config.use_residual else 0.0,
                    }
                    self._operations.append(operation)
                    if self.c1_config.use_residual:
                        target.active = False
                        target.effective_weight = 0.0
                        target.assertion_status = "superseded"
                        target.superseded_by = replacement.evidence_id

    def _detect_isolated_instance_conflicts(self):
        scopes_by_domain = {}
        for evidence in self._ledger:
            if not evidence.active or evidence.vote <= 0:
                continue
            domain = self.concepts[evidence.concept]["domain"]
            instance_scope = evidence.scope.split("/", 1)[0]
            scopes_by_domain.setdefault(domain, set()).add(instance_scope)
        for domain, scopes in scopes_by_domain.items():
            if len(scopes) > 1 and any(scope != "instance:shared" for scope in scopes):
                self._forced_unresolved_domains.add(domain)
                self._operations.append({
                    "operation": "ISOLATE_CONFLICT",
                    "domain": domain,
                    "scopes": sorted(scopes),
                    "reason": "multiple discourse instances cannot share one Concept selection",
                })

    def extract_evidence(self, texts: List[str]):
        self._ledger = []
        self._operations = []
        self._forced_unresolved_domains = set()
        self._clauses = self.segment(texts)
        raw_matches = accepted_matches = 0
        for clause in self._clauses:
            raw_count, accepted_count = self._extract_clause(clause)
            raw_matches += raw_count
            accepted_matches += accepted_count
        if self.c1_config.use_correction:
            self._apply_corrections()
        if self.c1_config.use_scope:
            self._detect_isolated_instance_conflicts()
        lexical_patterns = len(self.data["lexicon"]) + len(self.data.get("ambiguous_lexicon", []))
        context_patterns = len(self.data.get("context_rules", [])) if self.c1_config.use_context else 0
        self._c1_diagnostics = {
            "clauses": len(self._clauses),
            "patterns_checked": len(self._clauses) * (lexical_patterns + context_patterns),
            "raw_surface_matches": raw_matches,
            "accepted_surface_matches": accepted_matches,
            "overlap_matches_suppressed": raw_matches - accepted_matches,
            "evidence_items": len(self._ledger),
            "active_evidence_items": sum(evidence.active for evidence in self._ledger),
            "superseded_evidence_items": sum(not evidence.active for evidence in self._ledger),
            "operations": len(self._operations),
        }
        return self._ledger

    def score(self, texts: List[str]):
        evidence = self.extract_evidence(texts)
        scores = {
            concept_id: ConceptScore(
                concept_id,
                concept["label_ja"],
                concept["domain"],
                depth=self.depth(concept_id),
            )
            for concept_id, concept in self.concepts.items()
        }
        for item in evidence:
            if not item.active or item.effective_weight <= 0:
                continue
            score = scores[item.concept]
            if item.vote > 0:
                if item.reason == "context boost":
                    score.context_boost += item.effective_weight
                else:
                    score.direct_support += item.effective_weight
            else:
                score.contradiction += item.effective_weight

        if self.config.use_hierarchy:
            for concept_id, score in list(scores.items()):
                base = score.direct_support + score.context_boost
                if base > 0:
                    for ancestor, distance in self.ancestors(concept_id):
                        scores[ancestor].propagated_support += base * (0.55 ** distance)
        if self.config.use_sibling_contradiction:
            for concept_id, score in list(scores.items()):
                positive = score.direct_support + score.context_boost
                if positive > 0:
                    for sibling in self.siblings(concept_id):
                        scores[sibling].contradiction += positive * 0.65

        max_depth = {}
        for score in scores.values():
            max_depth[score.domain] = max(max_depth.get(score.domain, 0), score.depth)
        for score in scores.values():
            if self.config.use_hierarchy:
                score.generality_penalty = max(0, max_depth[score.domain] - score.depth) * 0.10
            score.score = (
                score.direct_support
                + 0.80 * score.propagated_support
                + score.context_boost
                - 1.20 * score.contradiction
                - score.generality_penalty
            )
        return scores, evidence

    def _select_domain(self, domain: str, scores: Dict[str, ConceptScore]):
        selection = super()._select_domain(domain, scores)
        if domain in self._forced_unresolved_domains:
            selection = dict(selection)
            selection["selected"] = "UNRESOLVED"
            selection["selection_confidence"] = 0.85
            selection["ambiguous"] = True
            selection["reason"] = "isolated discourse scopes contain competing instances"
        return selection

    def analyze(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        scores, _ = self.score(texts)
        domains = sorted({concept["domain"] for concept in self.concepts.values()})
        ranking = {}
        for domain in domains:
            rows = sorted(
                [score for score in scores.values() if score.domain == domain],
                key=lambda score: (score.score, score.depth),
                reverse=True,
            )
            ranking[domain] = [
                {
                    "concept": score.concept,
                    "label_ja": score.label_ja,
                    "score": round(score.score, 4),
                    "direct_support": round(score.direct_support, 4),
                    "propagated_support": round(score.propagated_support, 4),
                    "contradiction": round(score.contradiction, 4),
                    "context_boost": round(score.context_boost, 4),
                    "depth": score.depth,
                }
                for score in rows
            ]
        diagnostics = dict(self._c1_diagnostics)
        diagnostics.update({
            "concepts_scored": len(scores),
            "candidates_by_domain": {domain: len(ranking[domain]) for domain in domains},
            "forced_unresolved_domains": sorted(self._forced_unresolved_domains),
        })
        return {
            "version": "PLM-C1 v0.1",
            "inputs": texts,
            "config": asdict(self.c1_config),
            "clauses": [asdict(clause) for clause in self._clauses],
            "operations": self._operations,
            "selections": {domain: self._select_domain(domain, scores) for domain in domains},
            "ranking": ranking,
            "evidence": [asdict(item) for item in self._ledger],
            "diagnostics": diagnostics,
        }
