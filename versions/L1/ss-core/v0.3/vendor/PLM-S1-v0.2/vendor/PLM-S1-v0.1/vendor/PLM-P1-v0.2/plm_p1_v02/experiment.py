"""Paired equal-energy comparison; evaluator alone owns truth/channel parameters."""
from dataclasses import asdict
from statistics import NormalDist
import numpy as np
from plm_p1.core import PhaseCodebook, encode, decode, channel, DecodePolicy, canonical
from plm_p1.evaluation import summarize
from .fixtures import make_frames, entity_candidates, public_catalogue, DOC
from .recovery import Receiver, AdaptivePolicy, candidate_list
from .partition import encode_partitioned, template

METHODS = ["v01_fixed", "mixed_adaptive", "projected_fixed", "projected_adaptive", "partitioned_fixed"]


def fixed_from_scores(scores, choices, observed):
    order = sorted(range(len(choices)), key=lambda i: (-scores[i], canonical(choices[i])))
    best = order[0]
    margin = float(scores[best] - max(0, scores[order[1]] if len(order) > 1 else 0))
    selected = choices[best] if observed >= 64 and scores[best] >= .65 and margin >= .20 else None
    return {"selected": selected, "reason": "numerical_recovery_only" if selected else "fixed_policy_abstain",
            "top_candidates": [{"symbol": choices[i], "score": round(float(scores[i]), 8)} for i in order[:5]], "margin": round(margin, 8)}


def projected_fixed(receiver, doc, event, role, choices):
    choices = candidate_list(choices)
    n = int(receiver.mask.sum())
    if n < 128:
        return {"selected": None, "reason": "insufficient_observed_components", "top_candidates": [], "margin": None}
    q, y, rank = receiver.context(doc, event, role)
    if n - rank < 128:
        return {"selected": None, "reason": "insufficient_residual_degrees_of_freedom", "top_candidates": [], "margin": None}
    a = np.column_stack([receiver.book.key(doc, event, role)[receiver.mask] * receiver.book.value(c)[receiver.mask] for c in choices])
    t = a - q @ (q.conj().T @ a) if rank else a
    e = np.sum(abs(t)**2, axis=0)
    if np.any(e < .5*n):
        return {"selected": None, "reason": "candidate_subspace_too_depleted", "top_candidates": [], "margin": None}
    return fixed_from_scores(np.real(t.conj().T @ y) / e, choices, n)


def partitioned_fixed(values, mask, book, doc, event, role, choices):
    choices = candidate_list(choices)
    templates = np.column_stack([template(book, doc, event, role, c)[mask] for c in choices])
    e = np.sum(abs(templates)**2, axis=0)
    n = int(np.count_nonzero(templates[:, 0]))
    if n < 64:
        return {"selected": None, "reason": "insufficient_observed_components", "top_candidates": [], "margin": None}
    scores = np.real(templates.conj().T @ values[mask]) / e
    return fixed_from_scores(scores, choices, n)


def trial(code_seed, channel_seed, condition, *, methods=METHODS, policy=AdaptivePolicy()):
    book = PhaseCodebook(condition.get("dimension", 2048), "p1-v02-code-" + str(code_seed))
    frames = make_frames(condition["events"])
    candidates = entity_candidates(condition.get("candidates", 96))
    catalogue = public_catalogue(condition["events"])
    if condition.get("unknown_nuisance"):
        # OOV is evaluator-side perturbation, NOT silently added to the public catalogue.
        from plm_p1.core import symbol
        for f in frames:
            f["slots"]["predicate"] = symbol("predicate", "outside-public-vocabulary")
    channels, budget = {}, {}
    bindings = sum(len(f["slots"]) for f in frames)
    for codec in {"partitioned" if m == "partitioned_fixed" else "mixed" for m in methods}:
        memory = encode_partitioned(frames, book) if codec == "partitioned" else encode(frames, book)
        gain = float(np.sqrt(bindings * book.dimension / np.vdot(memory, memory).real))
        transmitted = memory * gain
        values, mask = channel(transmitted, seed=channel_seed, **{k: condition[k] for k in ("keep_fraction", "noise_std", "phase_offset", "jitter_std")})
        # This single public gain is shared side information for every receiver.
        channels[codec] = (values / gain, mask)
        budget[codec] = {"dimension": book.dimension, "bindings": bindings, "transmit_energy": round(float(np.vdot(transmitted, transmitted).real), 6), "public_gain": round(gain, 10)}
    values, mask = channels.get("mixed", (None, None))
    projected = Receiver(values, mask, book, catalogue) if values is not None else None
    plain = Receiver(values, mask, book, catalogue, project=False) if values is not None else None
    rows = []
    for frame in frames[:4]:
        for role in ("subject", "object"):
            truth = frame["slots"][role]
            for kind in ("present", "absent_event", "true_value_not_in_dictionary"):
                event = "absent-" + frame["event_id"] if kind == "absent_event" else frame["event_id"]
                choices = [c for c in candidates if c != truth] if kind == "true_value_not_in_dictionary" else candidates
                for method in methods:
                    if method == "v01_fixed":
                        r = decode(values, book, DOC, event, role, choices, mask=mask)
                    elif method == "mixed_adaptive":
                        r = plain.scores(DOC, event, role, choices, policy)
                    elif method == "projected_fixed":
                        r = projected_fixed(projected, DOC, event, role, choices)
                    elif method == "projected_adaptive":
                        r = projected.scores(DOC, event, role, choices, policy)
                    else:
                        y2, m2 = channels["partitioned"]
                        r = partitioned_fixed(y2, m2, book, DOC, event, role, choices)
                    outcome = ("correct" if r["selected"] == truth else "abstained" if r["selected"] is None else "wrong") if kind == "present" else ("false_accept" if r["selected"] is not None else "correct_rejection")
                    rows.append({"code_seed": code_seed, "channel_seed": channel_seed, "condition": condition["name"], "method": method,
                                 "event_id": event, "role": role, "test_kind": kind, "outcome": outcome,
                                 "selected": r["selected"], "reason": r["reason"], "margin": r["margin"],
                                 "top_score": r["top_candidates"][0]["score"] if r["top_candidates"] else None,
                                 "observed_components": int((channels["partitioned"][1] if method == "partitioned_fixed" else mask).sum()),
                                 **{k: r[k] for k in ("residual_dof", "nuisance_rank", "residual_power", "amplitude_threshold", "margin_threshold") if k in r}})
    return rows, budget


def aggregates(rows):
    out = []
    for condition, method in sorted({(r["condition"], r["method"]) for r in rows}):
        group = [r for r in rows if r["condition"] == condition and r["method"] == method]
        by_code = [{"code_seed": s, **summarize([r for r in group if r["code_seed"] == s])} for s in sorted({r["code_seed"] for r in group})]
        by_channel = [{"channel_seed": s, **summarize([r for r in group if r["channel_seed"] == s])} for s in sorted({r["channel_seed"] for r in group})]
        out.append({"condition": condition, "method": method, **summarize(group), "by_code_seed": by_code, "by_channel_seed": by_channel})
    return out
