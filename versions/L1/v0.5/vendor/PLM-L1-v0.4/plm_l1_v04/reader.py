"""Local role recovery and learned component-consistency check, no grammar oracle."""
from .algebra import require
from .lexicon import tokenize, CONTENT, GOALS
from .features import role_context, split_gaps, status_context
from .runtime import abstain


def read(model, text):
    try:
        kinds = model.meta["kinds"]
        tokens = tokenize(text, kinds)
        meaning, positions, audit = {}, {}, []
        for i, token in enumerate(tokens):
            if kinds[token] != "marker":
                recalled = model.memories["roles"].recall(role_context(tokens, i, kinds))
                role = recalled["value"]
                require(role in CONTENT and role not in meaning, "unresolved_or_duplicate_role")
                value = model.memories["lexical_read"].recall({"surface": token})["value"]
                require(value in model.meta["slot_candidates"][role], "unresolved_lexical_value")
                meaning[role], positions[i] = value, role
                audit.append({"position": i, "role": recalled})
        order, gaps = split_gaps(tokens, positions)
        require(order[0] in GOALS and model.order(order[0]) == order, "unlearned_content_order")
        context = status_context(tokens, kinds, gaps, order)
        for slot in ("polarity", "modality"):
            recalled = model.memories[slot].recall(context)
            require(recalled["value"] in model.meta["slot_candidates"][slot], "unresolved_status")
            meaning[slot] = recalled["value"]
        # Reuse learned forward gap associations, not a hand-written language
        # rule. This rejects mismatched prefix/suffix, punctuation and markers.
        for anchor, markers in gaps.items():
            require(model.gap(meaning, order[0], anchor) == markers, "component_consistency_failed")
        return {"status": "read", "packet": model.encode(meaning), "audit": audit, "eligible_for_inference": False}
    except (ValueError, TypeError) as error:
        return abstain(str(error))
