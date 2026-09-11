"""Signal codec and learned component assembly; no reader/trainer imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require
from .lexicon import CONTENT, ROLES, GOALS, validate_meaning
from .features import START, gap_context
from .projection import Space, ProjectionMemory

MEMORIES = ("roles", "polarity", "modality", "order_support", "order_output", "gaps", "lexical_read", "lexical_write")


def abstain(reason, **extra):
    return {"status": "abstain", "reason": reason, "text": None, "packet": None, "eligible_for_inference": False, **extra}


class Model:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-parts-v1" and self.meta.get("eligible_for_inference") is False, "invalid_metadata")
        require(set(memories) == set(MEMORIES) and set(self.meta["slot_candidates"]) == set(ROLES), "invalid_inventory")
        self.memories = memories
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.fingerprint = digest({"metadata": self.meta, "memories": {name: [
            {"mask": list(mask), "hash": hashlib.sha256(vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(candidates)}
            for mask, vector, candidates, _ in memory.groups] for name, memory in sorted(memories.items())}})
        self.basis = {r: np.array([self.book.code("value", v).conj() for v in self.meta["slot_candidates"][r]]) for r in ROLES}

    def encode(self, meaning):
        validate_meaning(meaning, self.meta["slot_candidates"])
        vector = sum(self.book.code("semantic_role", r) * self.book.code("value", meaning[r]) for r in ROLES)
        return {"schema": "plm-l1-parts-meaning-v1", "model_fingerprint": self.fingerprint, "dimension": self.book.dimension,
                "real": vector.real.tolist(), "imag": vector.imag.tolist(), "eligible_for_inference": False}

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
            require(packet["schema"] == "plm-l1-parts-meaning-v1" and packet["model_fingerprint"] == self.fingerprint, "packet_model_mismatch")
            require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension and packet["eligible_for_inference"] is False, "invalid_contract")
            for field in ("real", "imag"):
                require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(v) in (int, float) for v in packet[field]), "invalid_signal_values")
            vector = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
            require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32., "invalid_signal")
            clean = np.zeros(self.book.dimension, dtype=np.complex128)
            meaning = {}
            for role in ROLES:
                scores = np.real(self.basis[role] @ (vector * self.book.code("semantic_role", role).conj())) / self.book.dimension
                order = np.argsort(-scores, kind="stable")
                top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
                require(top >= .65 and top-runner >= .25, "ambiguous_meaning")
                meaning[role] = self.meta["slot_candidates"][role][order[0]]
                clean += self.book.code("semantic_role", role) * self.book.code("value", meaning[role])
            residual = float(np.linalg.norm(vector-clean) / np.linalg.norm(clean))
            require(residual <= .20, "meaning_residual_excessive")
            return {"status": "recovered", "meaning": meaning, "residual": round(residual, 8), "eligible_for_inference": False}
        except (ValueError, TypeError, OverflowError) as error:
            return abstain(str(error), meaning=None)

    def order(self, goal):
        require(type(goal) is str and goal in GOALS, "unsupported_goal")
        result = self.memories["order_output"].recall({"goal": goal})
        require(result["value"] is not None, "unknown_order")
        order = json.loads(result["value"])
        require(type(order) is list and len(order) == len(CONTENT) and set(order) == set(CONTENT) and order[0] == goal, "invalid_order")
        require(self.memories["order_support"].recall({"order": order})["value"] == "supported", "unsupported_order")
        return order

    def gap(self, meaning, goal, anchor):
        recalled = self.memories["gaps"].recall(gap_context(meaning, goal, anchor))
        require(recalled["value"] is not None, "unresolved_marker_component")
        gap = json.loads(recalled["value"])
        require(type(gap) is list and len(gap) <= 9 and all(type(t) is str and self.meta["kinds"].get(t) == "marker" for t in gap), "invalid_marker_component")
        return gap

    def generate(self, packet, goal="object"):
        recovered = self.recover(packet)
        if recovered["status"] != "recovered":
            return abstain(recovered["reason"])
        meaning = recovered["meaning"]
        try:
            order = self.order(goal)
            tokens = self.gap(meaning, goal, START)
            trace = [{"anchor": START, "markers": list(tokens)}]
            for role in order:
                surface = self.memories["lexical_write"].recall({"meaning_value": meaning[role]})["value"]
                require(surface is not None and self.meta["kinds"].get(surface) in ("entity", "predicate"), "unknown_lexical_realization")
                gap = self.gap(meaning, goal, role)
                tokens += [surface] + gap
                trace.append({"anchor": role, "markers": gap})
            text = "".join(tokens)
            require(len(tokens) <= 9 and len(text) <= 256, "output_capacity_exceeded")
            return {"status": "generated", "text": text, "trace": trace, "eligible_for_inference": False}
        except ValueError as error:
            return abstain(str(error))

    def read(self, text):
        from .reader import read
        return read(self, text)

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "model.json").exists() and not (target / "weights.npz").exists(), "output_exists")
        groups, weights = {}, {}
        for name, memory in self.memories.items():
            groups[name] = []
            for i, (mask, vector, candidates, _) in enumerate(memory.groups):
                key = name + "_" + str(i)
                groups[name].append({"mask": list(mask), "candidates": list(candidates), "weight": key})
                weights[key] = vector
        info = {"metadata": self.meta, "fingerprint": self.fingerprint, "groups": groups}
        with (target / "model.json").open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        np.savez_compressed(target / "weights.npz", **weights)

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "model.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "groups"}, "invalid_model_envelope")
        meta = info["metadata"]
        space = Space(Book(meta["dimension"], meta["seed"]))
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            expected = {g["weight"] for groups in info["groups"].values() for g in groups}
            require(expected == set(weights.files), "invalid_weight_inventory")
            memories = {name: ProjectionMemory(space, [(g["mask"], weights[g["weight"]], g["candidates"]) for g in groups]) for name, groups in info["groups"].items()}
        model = cls(meta, memories)
        require(model.fingerprint == info["fingerprint"], "model_hash_mismatch")
        return model
