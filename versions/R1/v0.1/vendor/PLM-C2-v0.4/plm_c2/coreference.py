from dataclasses import dataclass
import re
from plm_c2_v02.engine import ReferenceLink as OldReferenceLink
from .semantics import match_span


@dataclass
class ReferenceLink(OldReferenceLink):
    antecedent_entity_id: str = ""
    antecedent_mention_id: str = ""
    reference_mention_id: str = ""


class InstanceCoreference:
    """Local mention identity, distinct from Concept taxonomy and target scopes."""

    def _mention(self, clause, source_span, concepts=None, number="singular", kind="nominal", entity_id=None):
        for mention in self._mentions:
            if (mention["clause_id"] == clause.clause_id and mention["span"] == source_span
                    and mention["kind"] == kind and (entity_id is None or mention["entity_id"] == entity_id)):
                return mention
        if entity_id is None and kind != "unresolved_reference":
            existing = next((m for m in self._mentions if m["clause_id"] == clause.clause_id
                             and m["span"] == source_span and m["entity_id"] is not None
                             and m["kind"] in {"nominal", "argument"}), None)
            entity_id = existing["entity_id"] if existing else None
        if entity_id is None and kind != "unresolved_reference":
            entity_id = f"ENT{len(self._entities) + 1:06d}"
            self._entities.append({"entity_id": entity_id, "concept_candidates": sorted(set(concepts or [])),
                                   "number": number, "identity_status": "local_mention", "kind": kind})
        mention = {"mention_id": f"MN{len(self._mentions) + 1:06d}", "entity_id": entity_id,
                   "source_id": clause.source_id, "clause_id": clause.clause_id, "span": source_span,
                   "concept_candidates": sorted(set(concepts or [])), "number": number, "kind": kind}
        self._mentions.append(mention)
        return mention

    def _build_instance_mentions(self):
        if self._instance_mentions_built:
            return
        self._instance_mentions_built = True
        for clause in self._clauses:
            occurrence_counts = {}
            text = self.normalize(clause.text)
            if len(text) != len(clause.text):
                continue  # no misleading offsets for length-changing normalization
            for match in self._surface_matches(text):
                item = match["item"]
                concepts = [item["concept"]] if match["kind"] == "lexicon" else [x["concept"] for x in item["candidates"]]
                if not any(self.concepts[c]["domain"] in {"entity", "place"} for c in concepts):
                    continue
                start, end = match["start"], match["end"]
                surface = clause.text[start:end]
                plural = (re.search(r"\b(?:two|three|several|many|[2-9])\s*$", text[:start])
                          or surface.lower() in {"dogs", "cats", "humans", "people", "animals", "banks"}
                          or re.match(r"[二三2345]匹", clause.text[end:]))
                mention = self._mention(clause, {"start": start, "end": end, "text": surface},
                                        concepts, "plural" if plural else "singular")
                mention["evidence_ids"] = []
                for concept in concepts:
                    key = (item["pattern"], concept)
                    ordinal = occurrence_counts.get(key, 0)
                    occurrence_counts[key] = ordinal + 1
                    matching = [e for e in self._ledger if e.clause_id == clause.clause_id
                                and e.pattern == item["pattern"] and e.concept == concept
                                and e.reason in self.LEXICAL_REASONS | {"composed polarity negation"}]
                    if ordinal < len(matching):
                        mention["evidence_ids"].append(matching[ordinal].evidence_id)

    def _antecedent_instances(self, clause):
        evidence_by_id = {e.evidence_id: e for e in self._ledger}
        for previous in reversed(self._clauses[:self._clauses.index(clause)]):
            if previous.instance_scope != clause.instance_scope:
                break
            found = []
            for mention in self._mentions:
                if mention["clause_id"] != previous.clause_id or mention["kind"] != "nominal":
                    continue
                evidence = [evidence_by_id[eid] for eid in mention.get("evidence_ids", [])]
                if any(e.active and e.vote > 0 and e.assertion_status in {"asserted", "corrective", "provisional"}
                       and self.concepts[e.concept]["domain"] == "entity" for e in evidence):
                    found.append(mention)
            if found:
                return previous, found
        return None, []

    def _resolve_ordered_references(self):
        if not self.config.use_instance_coreference:
            return super()._resolve_ordered_references()
        self._build_instance_mentions()
        for clause in self._clauses:
            if any(m["clause_id"] == clause.clause_id and any(self.concepts[c]["domain"] == "entity"
                   for c in m["concept_candidates"]) for m in self._mentions if m["kind"] == "nominal"):
                continue
            cue = self.ORDERED_REFERENCE_CUES.search(clause.text) if self.config.use_ordered_coreference else None
            mode = "ordered"
            if not cue and self.config.use_extended_coreference:
                cue = self.PAIR_REFERENCE_CUES.search(clause.text)
                if not cue:
                    cue, mode = self.PLURAL_REFERENCE_CUES.search(clause.text), "plural"
                if not cue:
                    cue, mode = self.SINGULAR_REFERENCE_CUES.search(clause.text), "singular"
            if not cue:
                continue
            previous, candidates = self._antecedent_instances(clause)
            cue_text, chosen = cue.group().lower(), []
            if mode == "ordered" and len(candidates) >= 2 and all(m["number"] == "singular" for m in candidates):
                first = bool(re.search(r"former|first|earlier|前者", cue_text))
                chosen = [candidates[0] if first else candidates[1] if "second" in cue_text else candidates[-1]]
            elif mode == "singular" and len(candidates) == 1 and candidates[0]["number"] == "singular":
                chosen = candidates
            elif mode == "plural" and (len(candidates) >= 2 or (candidates and candidates[0]["number"] == "plural")):
                chosen = candidates
            self._reference_resolutions.append({
                "clause_id": clause.clause_id, "cue": cue.group(), "mode": mode,
                "status": "resolved" if chosen else "ambiguous" if candidates else "unresolved",
                "candidate_entity_ids": [m["entity_id"] for m in candidates],
                "resolved_entity_ids": [m["entity_id"] for m in chosen],
            })
            if not chosen:
                self._mention(clause, match_span(clause.text, cue), kind="unresolved_reference")
                continue
            emitted_concepts = set()
            for antecedent in chosen:
                evidences = [e for e in self._ledger if e.evidence_id in antecedent.get("evidence_ids", []) and e.active and e.vote > 0]
                if not evidences:
                    continue
                evidence = evidences[0]
                reference = self._mention(clause, match_span(clause.text, cue), antecedent["concept_candidates"],
                                          number=antecedent["number"], kind="reference", entity_id=antecedent["entity_id"])
                if evidence.concept not in emitted_concepts:
                    self._append_evidence(clause, f"[reference:{cue.group()}]", evidence.concept, 1, 1.05, "instance coreference")
                    emitted_concepts.add(evidence.concept)
                link = ReferenceLink(f"Q{len(self._reference_links) + 1:04d}", clause.clause_id,
                                     previous.clause_id, cue.group(), evidence.concept, evidence.evidence_id,
                                     antecedent["entity_id"], antecedent["mention_id"], reference["mention_id"])
                self._reference_links.append(link)
                self._operations.append({"operation": "RESOLVE_INSTANCE_REFERENCE", "reference_id": link.link_id,
                                         "antecedent_entity_id": antecedent["entity_id"]})

    def _resolve_extended_references(self):
        if not self.config.use_instance_coreference:
            return super()._resolve_extended_references()
