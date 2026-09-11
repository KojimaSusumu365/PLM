from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional
import json
import math
import re


@dataclass(frozen=True)
class EngineConfig:
    use_negation: bool = True
    use_context: bool = True
    use_hierarchy: bool = True
    use_sibling_contradiction: bool = True
    suppress_overlaps: bool = True
    strict_ascii_boundaries: bool = True


@dataclass
class Evidence:
    text_index: int
    source_text: str
    pattern: str
    concept: str
    vote: int
    weight: float
    reason: str


@dataclass
class ConceptScore:
    concept: str
    label_ja: str
    domain: str
    direct_support: float = 0.0
    propagated_support: float = 0.0
    contradiction: float = 0.0
    context_boost: float = 0.0
    generality_penalty: float = 0.0
    score: float = 0.0
    depth: int = 0


class PLMC0Engine:
    """PLM-C0 v0.3: inspectable ternary Concept consensus evaluator."""

    def __init__(self, data_path: Optional[str] = None, config: Optional[EngineConfig] = None):
        data_path = data_path or (Path(__file__).resolve().parents[1] / "data" / "concepts.json")
        with open(data_path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.config = config or EngineConfig()
        self.concepts = {c["id"]: c for c in self.data["concepts"]}
        self.children: Dict[str, List[str]] = {}
        for concept in self.data["concepts"]:
            if concept["parent"]:
                self.children.setdefault(concept["parent"], []).append(concept["id"])
        self._depth: Dict[str, int] = {}
        self._last_extraction_diagnostics: Dict[str, int] = {}

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower().replace("　", " "))

    def depth(self, concept_id: str) -> int:
        if concept_id in self._depth:
            return self._depth[concept_id]
        depth = 0
        current = concept_id
        while self.concepts[current]["parent"]:
            current = self.concepts[current]["parent"]
            depth += 1
        self._depth[concept_id] = depth
        return depth

    def ancestors(self, concept_id: str):
        output = []
        current = concept_id
        distance = 0
        while self.concepts[current]["parent"]:
            current = self.concepts[current]["parent"]
            distance += 1
            output.append((current, distance))
        return output

    def siblings(self, concept_id: str):
        parent = self.concepts[concept_id]["parent"]
        if not parent:
            return []
        return [child for child in self.children.get(parent, []) if child != concept_id]

    def _pattern_regex(self, pattern: str) -> str:
        escaped = re.escape(pattern.lower())
        if self.config.strict_ascii_boundaries and pattern.isascii() and any(char.isalnum() for char in pattern):
            return rf"(?<!\w){escaped}(?!\w)"
        return escaped

    def _find_matches(self, text: str, pattern: str):
        return re.finditer(self._pattern_regex(pattern), text)

    def _trigger_present(self, text: str, trigger: str) -> bool:
        return re.search(self._pattern_regex(trigger), text) is not None

    @staticmethod
    def _negated(text: str, start: int, end: int) -> bool:
        before = text[max(0, start - 36):start]
        after = text[end:min(len(text), end + 18)]
        japanese_suffixes = (
            "ではない", "じゃない", "でない", "ではなく", "じゃなく", "でなく",
            "ではなかった", "じゃなかった", "でなかった",
        )
        if any(after.startswith(suffix) for suffix in japanese_suffixes):
            return True
        return bool(
            re.search(
                r"(?:\bnot|\bno|\bnever|\bwithout)\s+(?:(?:a|an|the)\s+)?(?:\w+[ -]){0,2}$",
                before,
            )
        )

    def _surface_matches(self, text: str):
        matches = []
        for item in self.data["lexicon"]:
            for match in self._find_matches(text, item["pattern"]):
                matches.append({"start": match.start(), "end": match.end(), "kind": "lexicon", "item": item})
        for item in self.data.get("ambiguous_lexicon", []):
            for match in self._find_matches(text, item["pattern"]):
                matches.append({"start": match.start(), "end": match.end(), "kind": "ambiguous", "item": item})

        if not self.config.suppress_overlaps:
            return sorted(matches, key=lambda row: (row["start"], row["end"]))

        accepted = []
        for candidate in sorted(
            matches,
            key=lambda row: (-(row["end"] - row["start"]), row["start"], row["item"]["pattern"]),
        ):
            overlaps = any(
                candidate["start"] < chosen["end"] and chosen["start"] < candidate["end"]
                for chosen in accepted
            )
            if not overlaps:
                accepted.append(candidate)
        return sorted(accepted, key=lambda row: (row["start"], row["end"]))

    def extract_evidence(self, texts: List[str]) -> List[Evidence]:
        output = []
        raw_match_count = 0
        accepted_match_count = 0
        lexical_patterns = len(self.data["lexicon"]) + len(self.data.get("ambiguous_lexicon", []))
        context_patterns = len(self.data.get("context_rules", [])) if self.config.use_context else 0

        for index, raw in enumerate(texts):
            text = self.normalize(raw)
            raw_matches = []
            for item in self.data["lexicon"]:
                raw_matches.extend(self._find_matches(text, item["pattern"]))
            for item in self.data.get("ambiguous_lexicon", []):
                raw_matches.extend(self._find_matches(text, item["pattern"]))
            raw_match_count += len(raw_matches)

            matches = self._surface_matches(text)
            accepted_match_count += len(matches)
            for match in matches:
                negated = self.config.use_negation and self._negated(text, match["start"], match["end"])
                vote = -1 if negated else 1
                reason = "local negation" if negated else "direct lexical support"
                item = match["item"]
                if match["kind"] == "lexicon":
                    output.append(Evidence(
                        index, raw, item["pattern"], item["concept"], vote,
                        float(item["weight"]), reason,
                    ))
                else:
                    for candidate in item["candidates"]:
                        output.append(Evidence(
                            index, raw, item["pattern"], candidate["concept"], vote,
                            float(candidate["weight"]),
                            "ambiguous candidate negated" if negated else "ambiguous lexical candidate",
                        ))

            if self.config.use_context:
                for rule in self.data.get("context_rules", []):
                    if any(self._trigger_present(text, trigger) for trigger in rule["trigger"]):
                        for concept_id, weight in rule.get("boost", {}).items():
                            output.append(Evidence(
                                index, raw, "[context]", concept_id, 1,
                                float(weight), "context boost",
                            ))
                        for concept_id, weight in rule.get("suppress", {}).items():
                            output.append(Evidence(
                                index, raw, "[context]", concept_id, -1,
                                float(weight), "context contradiction",
                            ))

        self._last_extraction_diagnostics = {
            "patterns_checked": len(texts) * (lexical_patterns + context_patterns),
            "raw_surface_matches": raw_match_count,
            "accepted_surface_matches": accepted_match_count,
            "overlap_matches_suppressed": raw_match_count - accepted_match_count,
        }
        return output

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
            score = scores[item.concept]
            if item.vote > 0:
                if item.reason == "context boost":
                    score.context_boost += item.weight
                else:
                    score.direct_support += item.weight
            else:
                score.contradiction += item.weight

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

    def _is_ancestor(self, first: str, second: str) -> bool:
        return any(concept_id == first for concept_id, _ in self.ancestors(second))

    def _select_domain(self, domain: str, scores: Dict[str, ConceptScore]):
        candidates = sorted(
            [score for score in scores.values() if score.domain == domain],
            key=lambda score: (score.score, score.depth, score.direct_support),
            reverse=True,
        )
        positive = [score for score in candidates if score.score > 0]
        if not positive:
            return {
                "domain": domain,
                "selected": "UNRESOLVED",
                "confidence": 0.0,
                "selection_confidence": 1.0,
                "ambiguous": True,
                "reason": "no positive evidence",
            }

        top = positive[0]
        narrowed = top
        if self.config.use_hierarchy:
            eligible = [
                score for score in positive
                if score.direct_support >= 0.75
                and score.score >= max(0.45, top.score * 0.55)
                and score.contradiction < (score.direct_support + score.context_boost + 0.50)
            ]
            if eligible:
                narrowed = sorted(
                    eligible,
                    key=lambda score: (score.depth, score.score, score.direct_support),
                    reverse=True,
                )[0]

        if self.config.use_hierarchy:
            competitors = [
                score for score in positive
                if score.concept != narrowed.concept
                and not self._is_ancestor(score.concept, narrowed.concept)
                and not self._is_ancestor(narrowed.concept, score.concept)
            ]
        else:
            competitors = [score for score in positive if score.concept != narrowed.concept]
        runner_up = competitors[0] if competitors else None
        margin = narrowed.score - (runner_up.score if runner_up else 0.0)
        mass = narrowed.direct_support + narrowed.context_boost + 0.5 * narrowed.propagated_support
        confidence = 1 / (
            1 + math.exp(
                -(0.9 * narrowed.score + 0.55 * margin + 0.25 * mass - 0.5 * narrowed.contradiction)
            )
        )
        ambiguous = narrowed.score < 0.55 or bool(runner_up and margin < 0.30)
        selected = "UNRESOLVED" if ambiguous else narrowed.concept
        if narrowed.score < 0.55:
            reason = "evidence below selection threshold"
        elif runner_up and margin < 0.30:
            reason = "non-hierarchical candidates too close"
        elif self.config.use_hierarchy:
            reason = "hierarchy-aware ternary consensus"
        else:
            reason = "ternary consensus without hierarchy"
        return {
            "domain": domain,
            "selected": selected,
            "candidate": narrowed.concept,
            "label_ja": narrowed.label_ja,
            "confidence": round(confidence, 4),
            "selection_confidence": round(confidence if not ambiguous else 1.0 - confidence, 4),
            "ambiguous": ambiguous,
            "reason": reason,
            "score": round(narrowed.score, 4),
            "runner_up": runner_up.concept if runner_up else None,
            "margin": round(margin, 4),
        }

    def analyze(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        scores, evidence = self.score(texts)
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
        diagnostics = dict(self._last_extraction_diagnostics)
        diagnostics.update({
            "concepts_scored": len(scores),
            "candidates_by_domain": {domain: len(ranking[domain]) for domain in domains},
            "evidence_items": len(evidence),
        })
        return {
            "version": "PLM-C0 v0.3",
            "inputs": texts,
            "config": asdict(self.config),
            "selections": {domain: self._select_domain(domain, scores) for domain in domains},
            "ranking": ranking,
            "evidence": [asdict(item) for item in evidence],
            "diagnostics": diagnostics,
        }
