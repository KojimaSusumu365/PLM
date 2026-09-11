"""Pair-trained reader; no teacher states, operations or language-specific rules."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .compat import Book, Memory, canonical, digest, require
from .features import tokenize, abstract, descriptor, Space
from .memory import Association

ROLES = ("subject", "object", "predicate", "polarity", "modality")
ASSOCIATIONS = ("support", "roles", "states")


def abstain(reason, **extra):
    return dict(status="abstain", reason=reason, eligible_for_inference=False, **extra)


class PairReader:
    def __init__(self, metadata, memories, lexical):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-pair-reader-v1" and self.meta.get("eligible_for_inference") is False, "invalid reader metadata")
        require(set(memories) == set(ASSOCIATIONS), "invalid reader memory inventory")
        require(set(self.meta["slot_candidates"]) == set(ROLES), "invalid slot inventory")
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.space = Space(self.book, self.meta["ordered"])
        self.memories, self.lexical = memories, lexical
        all_memories = dict(memories, lexical=lexical)
        for memory in all_memories.values():
            require(memory.vector.shape == (self.book.dimension,), "weight dimension mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {
            name: {"hash": hashlib.sha256(memory.vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(memory.candidates)}
            for name, memory in sorted(all_memories.items())}})
        self.slot_basis = {r: np.array([self.book.code("value", value).conj() for value in self.meta["slot_candidates"][r]]) for r in ROLES}

    def query(self, name, shape, **kwargs):
        return self.memories[name].recall(descriptor(shape, ordered=self.meta["ordered"], **kwargs))

    def pack(self, vector):
        return {"schema": "plm-l1-pair-meaning-v1", "reader_fingerprint": self.fingerprint,
                "dimension": self.book.dimension, "real": vector.real.tolist(), "imag": vector.imag.tolist(),
                "eligible_for_inference": False}

    def unpack(self, packet):
        require(type(packet) is dict and set(packet) == {"schema", "reader_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
        require(packet["schema"] == "plm-l1-pair-meaning-v1" and packet["reader_fingerprint"] == self.fingerprint, "packet_reader_mismatch")
        require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension and packet["eligible_for_inference"] is False, "invalid_packet_contract")
        for field in ("real", "imag"):
            require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(x) in (int, float) for x in packet[field]), "invalid_signal_values")
        values = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
        require(np.isfinite(values).all() and np.max(np.abs(values)) <= 32., "nonfinite_or_excessive_signal")
        return values

    def read(self, text):
        try:
            tokens = tokenize(text, self.meta["token_kinds"])
        except ValueError as error:
            return abstain(str(error), packet=None)
        shape = abstract(tokens, self.meta["token_kinds"])
        support = self.query("support", shape)
        if support["value"] != "supported":
            return abstain("unsupported_or_ambiguous_shape", packet=None, audit={"support": support})
        vector = np.zeros(self.book.dimension, dtype=np.complex128)
        slots, audit = {}, {"support": support, "roles": [], "states": {}}
        for position, token in enumerate(tokens):
            kind = self.meta["token_kinds"][token]
            if kind == "marker":
                continue
            content = self.lexical.recall([("token", token)])
            selected = self.query("roles", shape, position=position, kind=kind)
            role = selected["value"]
            audit["roles"].append({"position": position, "role": selected, "content": content})
            if role not in ("subject", "object", "predicate") or content["value"] is None:
                return abstain("role_or_lexical_association_unresolved", packet=None, audit=audit)
            if role in slots or content["value"] not in self.meta["slot_candidates"][role]:
                return abstain("duplicate_or_invalid_role", packet=None, audit=audit)
            slots[role] = content["value"]
        if set(slots) != {"subject", "object", "predicate"}:
            return abstain("incomplete_content", packet=None, audit=audit)
        for slot in ("polarity", "modality"):
            selected = self.query("states", shape, slot=slot)
            audit["states"][slot] = selected
            if selected["value"] not in self.meta["slot_candidates"][slot]:
                return abstain("semantic_status_unresolved", packet=None, audit=audit)
            slots[slot] = selected["value"]
        for role in ROLES:
            vector += self.book.code("semantic_role", role) * self.book.code("value", slots[role])
        return {"status": "read", "reason": "pair_learned_observation", "packet": self.pack(vector), "audit": audit, "eligible_for_inference": False}

    def recover(self, packet):
        try:
            vector = self.unpack(packet)
        except (ValueError, TypeError, OverflowError) as error:
            return abstain(str(error), slots=None)
        slots, audit = {}, {}
        clean = np.zeros(self.book.dimension, dtype=np.complex128)
        for role in ROLES:
            scores = np.real(self.slot_basis[role] @ (vector * self.book.code("semantic_role", role).conj())) / self.book.dimension
            order = np.argsort(-scores, kind="stable")
            top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
            audit[role] = {"score": round(top, 8), "margin": round(top - runner, 8)}
            if top < self.meta["minimum"] or top - runner < self.meta["margin"]:
                return abstain("ambiguous_meaning", slots=None, audit=audit)
            slots[role] = self.meta["slot_candidates"][role][order[0]]
            clean += self.book.code("semantic_role", role) * self.book.code("value", slots[role])
        residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
        if residual > .20:
            return abstain("meaning_residual_excessive", slots=None, audit=audit)
        return {"status": "recovered", "slots": slots, "audit": audit, "residual": round(residual, 8), "eligible_for_inference": False}

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "reader.json").exists() and not (target / "weights.npz").exists(), "reader_output_exists")
        all_memories = dict(self.memories, lexical=self.lexical)
        info = {"metadata": self.meta, "fingerprint": self.fingerprint,
                "candidates": {name: list(memory.candidates) for name, memory in all_memories.items()}}
        with (target / "reader.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        np.savez_compressed(target / "weights.npz", **{name: memory.vector for name, memory in all_memories.items()})

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "reader.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "candidates"}, "invalid reader envelope")
        meta = info["metadata"]
        book = Book(meta["dimension"], meta["seed"])
        space = Space(book, meta["ordered"])
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            require(set(weights.files) == set(ASSOCIATIONS) | {"lexical"}, "invalid weight names")
            memories = {name: Association(space, weights[name], info["candidates"][name], meta["minimum"], meta["margin"]) for name in ASSOCIATIONS}
            lexical = Memory(book, weights["lexical"], info["candidates"]["lexical"])
        reader = cls(meta, memories, lexical)
        require(reader.fingerprint == info["fingerprint"], "reader_hash_mismatch")
        return reader
