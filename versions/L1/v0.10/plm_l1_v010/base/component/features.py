"""Designed, language-neutral decomposition into content order and marker gaps."""
from .algebra import canonical, require
from .lexicon import CONTENT, ROLES, GOALS, tokenize, aligned_examples

START = "start"


def abstract_token(token, kinds):
    return ["marker", token] if kinds[token] == "marker" else ["kind", kinds[token]]


def shape(tokens, kinds):
    return [abstract_token(t, kinds) for t in tokens]


def role_context(tokens, position, kinds):
    return {"kind": kinds[tokens[position]],
            "left": abstract_token(tokens[position - 1], kinds) if position else ["boundary", "start"],
            "right": abstract_token(tokens[position + 1], kinds) if position + 1 < len(tokens) else ["boundary", "end"],
            "whole_shape": shape(tokens, kinds)}


def split_gaps(tokens, positions):
    # positions maps content-token indices to their inferred semantic roles.
    gaps, order, anchor = {START: []}, [], START
    for i, token in enumerate(tokens):
        if i in positions:
            anchor = positions[i]
            require(anchor in CONTENT and anchor not in gaps, "duplicate_role")
            order.append(anchor)
            gaps[anchor] = []
        else:
            gaps[anchor].append(token)
    require(set(order) == set(CONTENT) and len(order) == len(CONTENT), "incomplete_content")
    return order, gaps


def status_context(tokens, kinds, gaps, order):
    return {"leading_markers": gaps[START], "subject_markers": gaps["subject"],
            "object_markers": gaps["object"], "predicate_markers": gaps["predicate"],
            "content_order": order, "whole_shape": shape(tokens, kinds)}


def gap_context(meaning, goal, anchor):
    return {"anchor": anchor, "polarity": meaning["polarity"], "modality": meaning["modality"], "goal": goal}


def observations(pairs, lexicon):
    examples = aligned_examples(pairs, lexicon)
    kinds = {t["surface"]: t["kind"] for t in lexicon["tokens"]}
    values = {t["surface"]: t["value"] for t in lexicon["tokens"]}
    rows = {name: [] for name in ("roles", "polarity", "modality", "order_support", "order_output", "gaps", "lexical_read", "lexical_write")}
    for pair, example in zip(pairs, examples):
        tokens = tokenize(pair["text"], kinds)
        meaning = pair["meaning"]
        positions = {}
        for i, token in enumerate(tokens):
            if kinds[token] != "marker":
                role = next(r for r in CONTENT if meaning[r] == values[token])
                positions[i] = role
                rows["roles"].append((role_context(tokens, i, kinds), role))
        order, gaps = split_gaps(tokens, positions)
        goal = order[0]
        context = status_context(tokens, kinds, gaps, order)
        for slot in ("polarity", "modality"):
            rows[slot].append((context, meaning[slot]))
        rows["order_support"].append(({"order": order}, "supported"))
        rows["order_output"].append(({"goal": goal}, canonical(order)))
        for anchor, gap in gaps.items():
            rows["gaps"].append((gap_context(meaning, goal, anchor), canonical(gap)))
    for token in lexicon["tokens"]:
        if token["kind"] != "marker":
            rows["lexical_read"].append(({"surface": token["surface"]}, token["value"]))
            rows["lexical_write"].append(({"meaning_value": token["value"]}, token["surface"]))
    return rows
