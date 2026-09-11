from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json, math, re

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
    """PLM-C0 v0.2: inspectable ternary Concept consensus proof-of-concept."""

    def __init__(self, data_path: Optional[str] = None):
        data_path = data_path or (Path(__file__).resolve().parents[1] / "data" / "concepts.json")
        with open(data_path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.concepts = {c["id"]: c for c in self.data["concepts"]}
        self.children: Dict[str, List[str]] = {}
        for c in self.data["concepts"]:
            if c["parent"]:
                self.children.setdefault(c["parent"], []).append(c["id"])
        self._depth = {}

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower().replace("　", " "))

    def depth(self, cid: str) -> int:
        if cid in self._depth: return self._depth[cid]
        d, cur = 0, cid
        while self.concepts[cur]["parent"]:
            cur = self.concepts[cur]["parent"]; d += 1
        self._depth[cid] = d
        return d

    def ancestors(self, cid: str):
        out, cur, dist = [], cid, 0
        while self.concepts[cur]["parent"]:
            cur = self.concepts[cur]["parent"]; dist += 1; out.append((cur, dist))
        return out

    def siblings(self, cid: str):
        p = self.concepts[cid]["parent"]
        return [] if not p else [x for x in self.children.get(p, []) if x != cid]

    @staticmethod
    def _negated(text: str, start: int, end: int) -> bool:
        before, after = text[max(0,start-14):start], text[end:min(len(text),end+10)]
        if any(after.startswith(x) for x in ("ではない","じゃない","でなく","ではなく","じゃなく")):
            return True
        return bool(re.search(r"(?:\bnot(?:\s+a|\s+an)?|\bno)\s*$", before))

    def extract_evidence(self, texts: List[str]) -> List[Evidence]:
        out = []
        for idx, raw in enumerate(texts):
            text = self.normalize(raw)
            for item in self.data["lexicon"]:
                pat = item["pattern"].lower()
                for m in re.finditer(re.escape(pat), text):
                    neg = self._negated(text, m.start(), m.end())
                    out.append(Evidence(idx, raw, item["pattern"], item["concept"], -1 if neg else 1,
                                        float(item["weight"]), "local negation" if neg else "direct lexical support"))
            for item in self.data.get("ambiguous_lexicon", []):
                pat = item["pattern"].lower()
                for m in re.finditer(r"\b" + re.escape(pat) + r"\b", text):
                    neg = self._negated(text, m.start(), m.end())
                    for c in item["candidates"]:
                        out.append(Evidence(idx, raw, item["pattern"], c["concept"], -1 if neg else 1,
                                            float(c["weight"]), "ambiguous lexical candidate"))
            for rule in self.data.get("context_rules", []):
                if any(t.lower() in text for t in rule["trigger"]):
                    for cid,w in rule.get("boost",{}).items(): out.append(Evidence(idx,raw,"[context]",cid,1,float(w),"context boost"))
                    for cid,w in rule.get("suppress",{}).items(): out.append(Evidence(idx,raw,"[context]",cid,-1,float(w),"context contradiction"))
        return out

    def score(self, texts: List[str]):
        evidence = self.extract_evidence(texts)
        scores = {cid: ConceptScore(cid,c["label_ja"],c["domain"],depth=self.depth(cid)) for cid,c in self.concepts.items()}
        for ev in evidence:
            s = scores[ev.concept]
            if ev.vote > 0:
                if ev.reason == "context boost": s.context_boost += ev.weight
                else: s.direct_support += ev.weight
            else:
                s.contradiction += ev.weight
        for cid,s in list(scores.items()):
            base = s.direct_support + s.context_boost
            if base > 0:
                for anc,dist in self.ancestors(cid): scores[anc].propagated_support += base*(0.55**dist)
        for cid,s in list(scores.items()):
            positive = s.direct_support + s.context_boost
            if positive > 0:
                for sib in self.siblings(cid): scores[sib].contradiction += positive*0.65
        maxd = {}
        for s in scores.values(): maxd[s.domain] = max(maxd.get(s.domain,0),s.depth)
        for s in scores.values():
            s.generality_penalty = max(0,maxd[s.domain]-s.depth)*0.10
            s.score = s.direct_support + 0.80*s.propagated_support + s.context_boost - 1.20*s.contradiction - s.generality_penalty
        return scores,evidence

    def _is_ancestor(self,a,b): return any(x==a for x,_ in self.ancestors(b))

    def _select_domain(self, domain: str, scores: Dict[str,ConceptScore]):
        cand = sorted([s for s in scores.values() if s.domain==domain], key=lambda s:(s.score,s.depth,s.direct_support), reverse=True)
        pos = [s for s in cand if s.score>0]
        if not pos: return {"domain":domain,"selected":"UNRESOLVED","confidence":0.0,"ambiguous":True,"reason":"no positive evidence"}
        top = pos[0]
        eligible = [s for s in pos if s.direct_support>=0.75 and s.score>=max(0.45,top.score*0.55) and s.contradiction<(s.direct_support+s.context_boost+0.50)]
        narrowed = sorted(eligible,key=lambda s:(s.depth,s.score,s.direct_support),reverse=True)[0] if eligible else top
        competitors = [s for s in pos if s.concept!=narrowed.concept and not self._is_ancestor(s.concept,narrowed.concept) and not self._is_ancestor(narrowed.concept,s.concept)]
        runner = competitors[0] if competitors else None
        margin = narrowed.score-(runner.score if runner else 0.0)
        mass = narrowed.direct_support+narrowed.context_boost+0.5*narrowed.propagated_support
        conf = 1/(1+math.exp(-(0.9*narrowed.score+0.55*margin+0.25*mass-0.5*narrowed.contradiction)))
        ambiguous = narrowed.score<0.55 or bool(runner and margin<0.30)
        return {"domain":domain,"selected":"UNRESOLVED" if ambiguous else narrowed.concept,"candidate":narrowed.concept,
                "label_ja":narrowed.label_ja,"confidence":round(conf,4),"ambiguous":ambiguous,
                "reason":"evidence below selection threshold" if narrowed.score<0.55 else ("non-hierarchical candidates too close" if runner and margin<0.30 else "hierarchy-aware ternary consensus"),
                "score":round(narrowed.score,4),"runner_up":runner.concept if runner else None,"margin":round(margin,4)}

    def analyze(self, texts):
        texts = [texts] if isinstance(texts,str) else list(texts)
        scores,evidence = self.score(texts)
        domains = sorted({c["domain"] for c in self.concepts.values()})
        ranking = {}
        for d in domains:
            rows = sorted([s for s in scores.values() if s.domain==d], key=lambda s:(s.score,s.depth), reverse=True)
            ranking[d] = [{"concept":s.concept,"label_ja":s.label_ja,"score":round(s.score,4),"direct_support":round(s.direct_support,4),"propagated_support":round(s.propagated_support,4),"contradiction":round(s.contradiction,4),"context_boost":round(s.context_boost,4),"depth":s.depth} for s in rows]
        patterns_per_text = len(self.data["lexicon"]) + len(self.data.get("ambiguous_lexicon", [])) + len(self.data.get("context_rules", []))
        return {
            "version":"PLM-C0 v0.2",
            "inputs":texts,
            "selections":{d:self._select_domain(d,scores) for d in domains},
            "ranking":ranking,
            "evidence":[asdict(e) for e in evidence],
            "diagnostics":{
                "concepts_scored":len(scores),
                "candidates_by_domain":{d:len(ranking[d]) for d in domains},
                "patterns_checked":len(texts)*patterns_per_text,
                "evidence_items":len(evidence),
            },
        }
