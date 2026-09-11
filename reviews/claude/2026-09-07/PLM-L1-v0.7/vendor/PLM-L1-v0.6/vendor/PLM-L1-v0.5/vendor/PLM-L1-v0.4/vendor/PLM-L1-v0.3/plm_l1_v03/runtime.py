"""Autoregressive phase writer. No reader, teacher, corpus or old model imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require
from .features import ROLES, CONTENT, GOALS, Space, END, validate_meaning
from .memory import Association

MEMORIES = ("support", "steps", "lexical")


def abstain(reason, **extra):
    return dict(status="abstain", reason=reason, text=None, eligible_for_inference=False, **extra)


class Writer:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-pair-writer-v1" and self.meta.get("eligible_for_inference") is False, "invalid_metadata")
        require(set(memories) == set(MEMORIES), "invalid_memory_inventory")
        require(set(self.meta["slot_candidates"]) == set(ROLES), "invalid_slot_inventory")
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.space = Space(self.book, self.meta["use_prefix"], self.meta["use_status"])
        self.memories = memories
        for memory in memories.values():
            require(memory.vector.shape == (self.book.dimension,), "weight_dimension_mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {
            name: {"sha256": hashlib.sha256(memory.vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(memory.candidates)}
            for name, memory in sorted(memories.items())}})
        self.slot_basis = {r: np.array([self.book.code("value", v).conj() for v in self.meta["slot_candidates"][r]]) for r in ROLES}

    def encode(self, meaning):
        """Explicit meaning-to-signal boundary; not a text parser or generator."""
        validate_meaning(meaning, self.meta["slot_candidates"])
        vector = sum(self.book.code("semantic_role", r) * self.book.code("value", meaning[r]) for r in ROLES)
        return {"schema": "plm-l1-writer-meaning-v1", "writer_fingerprint": self.fingerprint,
                "dimension": self.book.dimension, "real": vector.real.tolist(), "imag": vector.imag.tolist(), "eligible_for_inference": False}

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {"schema", "writer_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
            require(packet["schema"] == "plm-l1-writer-meaning-v1" and packet["writer_fingerprint"] == self.fingerprint, "packet_writer_mismatch")
            require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension and packet["eligible_for_inference"] is False, "invalid_packet_contract")
            for field in ("real", "imag"):
                require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(x) in (int, float) for x in packet[field]), "invalid_signal_values")
            vector = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32., "invalid_signal")
            clean = np.zeros(self.book.dimension, dtype=np.complex128)
            meaning, audit = {}, {}
            for role in ROLES:
                scores = np.real(self.slot_basis[role] @ (vector * self.book.code("semantic_role", role).conj())) / self.book.dimension
                order = np.argsort(-scores, kind="stable")
                top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
                require(top >= .65 and top - runner >= .25, "ambiguous_meaning")
                meaning[role] = self.meta["slot_candidates"][role][order[0]]
                audit[role] = {"score": round(top, 8), "margin": round(top - runner, 8)}
                clean += self.book.code("semantic_role", role) * self.book.code("value", meaning[role])
            residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
            require(residual <= .20, "meaning_residual_excessive")
            return {"status": "recovered", "meaning": meaning, "audit": audit, "residual": round(residual, 8)}
        except (ValueError, TypeError, OverflowError) as error:
            return {"status": "abstain", "reason": str(error), "meaning": None}

    def generate(self, packet, goal="object", *, max_steps=12):
        if type(goal) is not str or goal not in GOALS:
            return abstain("unsupported_goal")
        if type(max_steps) is not int or not 1 <= max_steps <= 64:
            return abstain("invalid_step_budget")
        decoded = self.recover(packet)
        if decoded["status"] != "recovered":
            return abstain(decoded["reason"])
        meaning = decoded["meaning"]
        support = self.memories["support"].recall(self.space.context(meaning, goal))
        if support["value"] != "supported":
            return abstain("unsupported_meaning_goal")
        prefix, text, used, trace = [], [], set(), []
        for step in range(max_steps):
            selected = self.memories["steps"].recall(self.space.context(meaning, goal, prefix))
            symbol = selected["value"]
            trace.append({"step": step, **selected})
            if symbol is None:
                return abstain("next_symbol_unresolved", trace=trace)
            if symbol == END:
                if used != set(CONTENT):
                    return abstain("premature_end", trace=trace)
                return {"status": "generated", "text": "".join(text), "trace": trace, "eligible_for_inference": False}
            kind, value = json.loads(symbol)
            if kind == "slot":
                if value not in CONTENT or value in used or (not used and value != goal):
                    return abstain("invalid_role_emission", trace=trace)
                surface = self.memories["lexical"].recall({"lexical_value": meaning[value]})["value"]
                if surface is None or self.meta["surfaces"].get(surface) not in ("entity", "predicate"):
                    return abstain("lexical_realization_unresolved", trace=trace)
                used.add(value)
            elif kind == "literal" and self.meta["surfaces"].get(value) == "marker":
                surface = value
            else:
                return abstain("invalid_emission", trace=trace)
            prefix.append(symbol)
            text.append(surface)
            if len(prefix) > 9 or len("".join(text)) > 256:
                return abstain("output_capacity_exceeded", trace=trace)
        return abstain("step_budget_exhausted", trace=trace)

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "writer.json").exists() and not (target / "weights.npz").exists(), "writer_output_exists")
        info = {"metadata": self.meta, "fingerprint": self.fingerprint, "candidates": {k: list(v.candidates) for k, v in self.memories.items()}}
        with (target / "writer.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        np.savez_compressed(target / "weights.npz", **{k: v.vector for k, v in self.memories.items()})

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "writer.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "candidates"} and set(info["candidates"]) == set(MEMORIES), "invalid_writer_envelope")
        meta = info["metadata"]
        space = Space(Book(meta["dimension"], meta["seed"]), meta["use_prefix"], meta["use_status"])
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            require(set(weights.files) == set(MEMORIES), "invalid_weight_names")
            memories = {k: Association(space, weights[k], info["candidates"][k]) for k in MEMORIES}
        writer = cls(meta, memories)
        require(writer.fingerprint == info["fingerprint"], "writer_hash_mismatch")
        return writer
