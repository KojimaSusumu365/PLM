from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
import re

from plm_c1_v02.engine import C1Config as V02Config
from plm_c1_v02.engine import Clause, PLMC1Engine as V02Engine
from plm_c1_v02.engine import RelationEvidence, ScopedEvidence


@dataclass(frozen=True)
class C1Config(V02Config):
    use_lemma_normalization: bool = True
    use_transition_roles: bool = True
    use_event_identity: bool = True
    use_compound_analysis: bool = True
    use_open_set_confidence: bool = True


@dataclass
class NormalizationEvent:
    normalization_id: str
    clause_id: str
    surface: str
    lemma: str
    method: str


class PLMC1Engine(V02Engine):
    """PLM-C1 v0.3: normalized forms, revision roles, and event identity."""

    PROVISIONAL_ROLE_CUES = re.compile(
        r"(?:\bformerly\b|\bpreviously\b|\bpreliminary\b|\bprovisional\b|"
        r"\bpresumed\b|\btentative(?:ly)?\b|当初|以前|暫定|仮判定|仮に判定)",
        re.IGNORECASE,
    )
    CORRECTIVE_ROLE_CUES = re.compile(
        r"(?:\bultimately\b|\bfinally\b|\bconclusive(?:ly)?\b|\bconclusion\b|"
        r"\bdetermined\b|\bestablished\b|\bverified\b|最終|確定|結論|確認済み)",
        re.IGNORECASE,
    )
    RETRACTION_ROLE_CUES = re.compile(
        r"(?:\bretract(?:ed|ion)?\b|\bwithdrawn\b|\bwithdraw\b|\bruled\s+out\b|"
        r"取り消し|取消し|撤回|除外)",
        re.IGNORECASE,
    )
    EVENT_SHIFT_CUES = re.compile(
        r"(?:\banother\s+(?:case|instance|subject|event)\b|"
        r"\ba\s+different\s+(?:case|instance|subject|event)\b|"
        r"\belsewhere\b|\bin\s+a\s+separate\s+case\b|"
        r"\bseparately\b|\blater\b|\bafterward\b|"
        r"別件|別事例|別の(?:事例|対象|個体|案件)|別ケース|その後)",
        re.IGNORECASE,
    )
    VERB_LEMMAS = {"bark", "bite", "vocalize"}
    APPROVED_COMPOUNDS = {
        "river": ("bed", "beds", "side", "sides", "front", "fronts", "mouth", "mouths"),
    }

    def __init__(self, data_path: Optional[str] = None, config: Optional[C1Config] = None):
        self.v03_config = config or C1Config()
        super().__init__(data_path=data_path, config=self.v03_config)
        self._normalizations: List[NormalizationEvent] = []

    def _inflected_ascii_pattern(self, pattern: str):
        escaped = re.escape(pattern.lower())
        if pattern in self.VERB_LEMMAS:
            if pattern.endswith("e"):
                stem = re.escape(pattern[:-1].lower())
                return rf"(?:{escaped}(?:s|d)?|{stem}ing)"
            return rf"{escaped}(?:s|ed|ing)?"
        if len(pattern) > 1 and pattern.endswith("y") and pattern[-2].lower() not in "aeiou":
            stem = re.escape(pattern[:-1].lower())
            return rf"{stem}(?:y|ies)"
        if pattern.endswith(("s", "x", "z", "ch", "sh")):
            return rf"{escaped}(?:es)?"
        return rf"{escaped}s?"

    def _pattern_regex(self, pattern: str) -> str:
        if not (
            pattern.isascii()
            and pattern.isalpha()
            and self.config.use_morphology
            and self.config.use_lemma_normalization
        ):
            return super()._pattern_regex(pattern)

        escaped = self._inflected_ascii_pattern(pattern)
        if self.config.use_compound_analysis and pattern in self.APPROVED_COMPOUNDS:
            compounds = "|".join(re.escape(value) for value in self.APPROVED_COMPOUNDS[pattern])
            escaped = rf"(?:{escaped}|{re.escape(pattern.lower())}(?:{compounds}))"
        if self.config.strict_ascii_boundaries:
            return rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
        return escaped

    def _classify_state(self, text: str):
        if not self.config.use_transition_roles:
            return V02Engine._classify_state(self, text)
        if self.HYPOTHETICAL_CUES.search(text):
            return "hypothetical"
        if self.RETRACTION_ROLE_CUES.search(text):
            return "retracted"
        if self.CORRECTIVE_CUES.search(text) or self.CORRECTIVE_ROLE_CUES.search(text):
            return "corrective"
        if self.PROVISIONAL_CUES.search(text) or self.PROVISIONAL_ROLE_CUES.search(text):
            return "provisional"
        return "asserted"

    def segment(self, texts: List[str]) -> List[Clause]:
        if not self.config.use_event_identity or not self.config.use_discourse_state:
            return super().segment(texts)

        clauses = []
        for source_order, raw in enumerate(texts):
            source_id = f"S{source_order + 1:03d}"
            parts = (
                self._clean_parts(self.PART_SPLIT_PATTERN.split(raw))
                if self.config.use_scope else [raw.strip()]
            )
            states = [self._classify_state(part) for part in parts]
            current_scope = "instance:shared"
            for clause_order, (text, state) in enumerate(zip(parts, states)):
                clause_id = f"{source_id}:C{clause_order + 1:03d}"
                if (
                    self.config.use_target_tracking
                    and state not in {"corrective", "provisional", "retracted"}
                    and self.EVENT_SHIFT_CUES.search(text)
                ):
                    current_scope = f"instance:{clause_id}"
                    self._operations.append({
                        "operation": "TARGET_SHIFT",
                        "clause_id": clause_id,
                        "target_scope": current_scope,
                        "reason": "event-identity transition cue",
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
                        "reason": "event-aware discourse clause boundary",
                    })
                if effective_state != "asserted":
                    self._operations.append({
                        "operation": "STATE_TRANSITION",
                        "clause_id": clause.clause_id,
                        "state": effective_state,
                        "reason": "discourse role classification",
                    })
        return clauses

    @staticmethod
    def _exact_surface_regex(pattern: str):
        escaped = re.escape(pattern.lower())
        return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)

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
                if surface == pattern.lower():
                    continue
                key = (pattern.lower(), surface)
                if key in seen:
                    continue
                seen.add(key)
                compound = any(
                    pattern == lemma and surface == lemma + suffix
                    for lemma, suffixes in self.APPROVED_COMPOUNDS.items()
                    for suffix in suffixes
                )
                method = "approved_compound" if compound else "inflection"
                event = NormalizationEvent(
                    normalization_id=f"N{len(self._normalizations) + 1:04d}",
                    clause_id=clause.clause_id,
                    surface=surface,
                    lemma=pattern.lower(),
                    method=method,
                )
                self._normalizations.append(event)
                self._operations.append({
                    "operation": "SEGMENT_COMPOUND" if compound else "NORMALIZE_MORPHOLOGY",
                    "normalization_id": event.normalization_id,
                    "clause_id": clause.clause_id,
                    "surface": surface,
                    "lemma": pattern.lower(),
                    "method": method,
                })

    def _extract_clause(self, clause: Clause):
        evidence_start = len(self._ledger)
        counts = super()._extract_clause(clause)
        self._record_normalizations(clause, evidence_start)
        return counts

    def _apply_corrections(self):
        if self.config.use_transition_roles and self.config.use_residual:
            retracted = {clause.clause_id for clause in self._clauses if clause.assertion_status == "retracted"}
            for evidence in self._ledger:
                if evidence.active and evidence.clause_id in retracted:
                    self._operations.append({
                        "operation": "RETRACT",
                        "evidence_id": evidence.evidence_id,
                        "concept": evidence.concept,
                        "clause_id": evidence.clause_id,
                        "residual_removed": evidence.effective_weight,
                        "reason": "explicit judgment retraction",
                    })
                    evidence.active = False
                    evidence.effective_weight = 0.0
                    evidence.assertion_status = "retracted"
        super()._apply_corrections()

    def extract_evidence(self, texts: List[str]):
        self._normalizations = []
        evidence = super().extract_evidence(texts)
        self._c1_diagnostics.update({
            "normalization_events": len(self._normalizations),
            "morphology_events": sum(event.method == "inflection" for event in self._normalizations),
            "compound_events": sum(event.method == "approved_compound" for event in self._normalizations),
        })
        return evidence

    def _select_domain(self, domain, scores):
        selection = super()._select_domain(domain, scores)
        if not self.config.use_open_set_confidence:
            return selection
        domain_evidence = [
            evidence for evidence in self._ledger
            if self.concepts[evidence.concept]["domain"] == domain
        ]
        if selection.get("reason") == "no positive evidence" and not domain_evidence:
            selection = dict(selection)
            selection["selection_confidence"] = 0.35
            selection["reason"] = "open-set abstention: no matching evidence"
            selection["open_set"] = True
        return selection

    def analyze(self, texts):
        result = super().analyze(texts)
        result["version"] = "PLM-C1 v0.3"
        result["normalizations"] = [asdict(event) for event in self._normalizations]
        result["diagnostics"].update({
            "normalization_events": len(self._normalizations),
            "morphology_events": sum(event.method == "inflection" for event in self._normalizations),
            "compound_events": sum(event.method == "approved_compound" for event in self._normalizations),
            "open_set_domains": sorted(
                domain for domain, selection in result["selections"].items()
                if selection.get("open_set")
            ),
        })
        return result
