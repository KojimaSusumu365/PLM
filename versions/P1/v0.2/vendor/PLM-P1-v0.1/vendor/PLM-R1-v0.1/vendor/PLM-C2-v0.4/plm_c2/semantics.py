"""Bounded, span-preserving role recognition. No general syntactic-parser claim."""
from __future__ import annotations

import re


VERBS = {
    "grant": ("grant", "grants", "granted", "granting"),
    "award": ("award", "awards", "awarded", "awarding"),
    "allocate": ("allocate", "allocates", "allocated", "allocating"),
    "invest": ("invest", "invests", "invested", "investing"),
    "donate": ("donate", "donates", "donated", "donating"),
    "subsidize": ("subsidize", "subsidizes", "subsidized", "subsidizing"),
    "support": ("support", "supports", "supported", "supporting"),
    "back": ("back", "backs", "backed", "backing"),
    "sponsor": ("sponsor", "sponsors", "sponsored", "sponsoring"),
    "fund": ("fund", "funds", "funded", "funding"),
    "finance": ("finance", "finances", "financed", "financing"),
    "underwrite": ("underwrite", "underwrites", "underwritten", "underwriting", "underwrote"),
    "lend": ("lend", "lends", "lent", "lending"),
}
LEMMA = {form: lemma for lemma, forms in VERBS.items() for form in forms}
PARTICIPLES = {forms[2] for forms in VERBS.values()}
VERB_RE = re.compile(r"\b(?:" + "|".join(sorted(LEMMA, key=len, reverse=True)) + r")\b", re.I)
BANK_RE = re.compile(r"\bbanks?\b", re.I)
AUX_RE = re.compile(
    r"^(?:(?:is|are|was|were|be|been|being|has|have|had|do|does|did|"
    r"can|could|may|might|must|shall|should|will|would|not|never|also|"
    r"only|just|[a-z]+ly|[a-z]+n't)\s+)*$", re.I,
)
NEGATION_RE = re.compile(r"\b(?:not|never|neither|no)\b|n't\b", re.I)
HYPOTHETICAL_RE = re.compile(r"\b(?:if|might|could|would|may|suppose|assuming)\b", re.I)
FINANCIAL_OBJECT_RE = re.compile(
    r"\b(?:aid|grants?|resources?|funds?|money|equipment|research|projects?|plans?|"
    r"programs?|programmes?|initiatives?|conservation|restoration|cleanup|"
    r"scholarships?|budgets?|credits?|capital|loans?|financing|studies|study)\b", re.I,
)
SPATIAL_RE = re.compile(r"\b(?:near|beside|along|by|next\s+to|on\s+the\s+shore\s+of)\b|沿い|近く|そば", re.I)
SOURCE_PREFIX_RE = re.compile(r"^\s*(?:(?:record|observation|note|report)\s*:\s*)+", re.I)


def span(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in ".。;；"):
        end -= 1
    return {"start": start, "end": end, "text": text[start:end]}


def match_span(text, match):
    return span(text, match.start(), match.end())


def bank_event(text):
    """Return at most one bounded event; ambiguous attachments are quarantined."""
    banks = list(BANK_RE.finditer(text))
    verbs = list(VERB_RE.finditer(text))
    if len(banks) != 1:
        return None
    bank = banks[0]
    # A passive sentence can put its agent after the predicate.
    for verb in verbs:
        if verb.end() >= bank.start() or verb.group().lower() not in PARTICIPLES:
            continue
        bridge = text[verb.end():bank.start()]
        if not re.fullmatch(r"\s+by\s+(?:(?:the|a|an)\s+)?", bridge, re.I):
            continue
        before = text[:verb.start()]
        aux = re.search(r"\b(?:is|are|was|were|has\s+been|have\s+been|had\s+been|"
                        r"will\s+be|would\s+be|could\s+be|might\s+be)\s+"
                        r"(?:(?:not|never|[a-z]+ly|being)\s+)*$", before, re.I)
        if not aux:
            continue
        prefix = SOURCE_PREFIX_RE.match(text)
        patient = span(text, prefix.end() if prefix else 0, aux.start())
        bank_tail = text[bank.end():].strip()
        if bank_tail and not re.match(r"^(?:[.;]|for\b|to\b|in\b|on\b)", bank_tail, re.I):
            continue  # e.g. "by the bank manager" is not a bank agent.
        return _event(text, bank, verb, patient, "passive", "agent", before)
    # A bank followed immediately by auxiliaries/adverbs and a verb.
    for verb in verbs:
        if verb.start() < bank.end():
            continue
        bridge = text[bank.end():verb.start()].lstrip()
        if not AUX_RE.fullmatch(bridge):
            continue
        form = verb.group().lower()
        lemma = LEMMA[form]
        # Singular bare "bank support structure" has no finite verb.
        if form == lemma and not bridge.strip() and bank.group().lower() == "bank":
            continue
        passive = form in PARTICIPLES and bool(re.search(
            r"\b(?:is|are|was|were|be|been|being)\b", bridge, re.I))
        if passive:
            by = re.match(r"\s+by\s+", text[verb.end():], re.I)
            if not by:
                return _event(text, bank, verb, span(text, bank.start(), bank.end()),
                              "passive", "patient", text[:verb.start()])
            actor = span(text, verb.end() + by.end(), len(text))
            result = _event(text, bank, verb, match_span(text, bank),
                            "passive", "patient", text[:verb.start()])
            result["agent"] = actor
            return result
        boundary = re.search(r",\s*(?:it|they|we|he|she|this|that)\b", text[verb.end():], re.I)
        object_end = verb.end() + boundary.start() if boundary else len(text)
        return _event(text, bank, verb, span(text, verb.end(), object_end),
                      "active", "agent", text[:verb.start()])
    return None


def _event(text, bank, verb, patient, voice, bank_role, before):
    # Polarity is local to the bank's predicate, not another earlier sentence.
    local = before[bank.end():] if voice == "active" else before
    negative = bool(NEGATION_RE.search(local))
    hypothetical = bool(HYPOTHETICAL_RE.search(text))
    supported = bank_role == "agent" and bool(FINANCIAL_OBJECT_RE.search(patient["text"]))
    return {
        "agent": match_span(text, bank) if bank_role == "agent" else None,
        "patient": patient,
        "predicate_span": match_span(text, verb),
        "predicate": LEMMA[verb.group().lower()],
        "voice": voice,
        "bank_role": bank_role,
        "polarity": "negative" if negative else "positive",
        "modality": "hypothetical" if hypothetical else "asserted",
        "supported": supported,
        "reason": "supported_institutional_role" if supported else
                  "bank_is_patient" if bank_role == "patient" else "unsupported_object",
    }
