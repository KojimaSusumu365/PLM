from __future__ import annotations

from pathlib import Path
from typing import Optional
import json
import re


class PositiveLexicalBaseline:
    """Positive-only lexical vote baseline.

    It deliberately has no negation, context, hierarchy, or sibling contradiction.
    Equal top scores are returned as UNRESOLVED instead of being broken by file order.
    """

    def __init__(self, data_path: Optional[str] = None):
        data_path = data_path or (Path(__file__).resolve().parents[1] / "data" / "concepts.json")
        with open(data_path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.concepts = {c["id"]: c for c in self.data["concepts"]}

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower().replace("　", " "))

    def analyze(self, texts):
        texts = [texts] if isinstance(texts, str) else list(texts)
        scores = {cid: 0.0 for cid in self.concepts}
        evidence_items = 0
        for raw in texts:
            text = self.normalize(raw)
            for item in self.data["lexicon"]:
                matches = list(re.finditer(re.escape(item["pattern"].lower()), text))
                scores[item["concept"]] += len(matches) * float(item["weight"])
                evidence_items += len(matches)
            for item in self.data.get("ambiguous_lexicon", []):
                matches = list(re.finditer(r"\b" + re.escape(item["pattern"].lower()) + r"\b", text))
                for candidate in item["candidates"]:
                    scores[candidate["concept"]] += len(matches) * float(candidate["weight"])
                    evidence_items += len(matches)

        domains = sorted({c["domain"] for c in self.concepts.values()})
        ranking = {}
        selections = {}
        for domain in domains:
            rows = sorted(
                (cid for cid, c in self.concepts.items() if c["domain"] == domain),
                key=lambda cid: (-scores[cid], cid),
            )
            ranking[domain] = [
                {
                    "concept": cid,
                    "label_ja": self.concepts[cid]["label_ja"],
                    "score": round(scores[cid], 4),
                }
                for cid in rows
            ]
            top_score = scores[rows[0]]
            tied = len(rows) > 1 and scores[rows[1]] == top_score
            selected = rows[0] if top_score > 0 and not tied else "UNRESOLVED"
            selections[domain] = {
                "domain": domain,
                "selected": selected,
                "ambiguous": selected == "UNRESOLVED",
                "score": round(top_score, 4),
                "reason": "positive lexical vote" if selected != "UNRESOLVED" else "no unique positive lexical winner",
            }

        patterns_per_text = len(self.data["lexicon"]) + len(self.data.get("ambiguous_lexicon", []))
        return {
            "version": "positive-lexical-baseline v0.2",
            "inputs": texts,
            "selections": selections,
            "ranking": ranking,
            "diagnostics": {
                "concepts_scored": len(scores),
                "candidates_by_domain": {d: len(ranking[d]) for d in domains},
                "patterns_checked": len(texts) * patterns_per_text,
                "evidence_items": evidence_items,
            },
        }
