"""Signal codec and learned component assembly; no reader/trainer imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
from ..thresholds import MIN_SCORE, MIN_MARGIN, MIN_PRESENCE, MIN_PROOF, MAX_RESIDUAL, LEGACY_MIN_SCORE
from ..thresholds import values as threshold_values

from .algebra import Book, canonical, digest, require
from .lexicon import CONTENT, ROLES, GOALS, validate_meaning
from .features import START, gap_context
from .banked import BankedMemory, MemoryBlock, MODES

MEMORIES = ("roles", "polarity", "modality", "order_support", "order_output", "gaps", "lexical_read", "lexical_write")


def abstain(reason, **extra):
    return {"status": "abstain", "reason": reason, "text": None, "packet": None, "eligible_for_inference": False, **extra}


class Model:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-component-v09" and self.meta.get("eligible_for_inference") is False, "invalid_metadata")
        require(self.meta.get("memory_mode") in MODES, "invalid_memory_mode")
        require(self.meta.get('thresholds') == threshold_values(), 'threshold_policy_mismatch')
        require(self.meta.get("read_acceptance") == "recover_equals_candidate_v1", "invalid_read_acceptance_policy")
        require(set(memories) == set(MEMORIES) and set(self.meta["slot_candidates"]) == set(ROLES), "invalid_inventory")
        self.memories = memories
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        for memory in memories.values():
            require(isinstance(memory, BankedMemory), "invalid_memory_type")
            for block in memory.blocks:
                m = block.meta()
                require(m["seed"] == self.meta["seed"] and m["budget"] == self.meta["dimension"] and m["mode"] == MODES[self.meta["memory_mode"]], "block_model_mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {name: [hashlib.sha256(b.blob).hexdigest() for b in memory.blocks] for name, memory in sorted(memories.items())}})
        self.basis = {r: np.array([self.book.code("value", v).conj() for v in self.meta["slot_candidates"][r]]) for r in ROLES}

    def encode(self, meaning):
        validate_meaning(meaning, self.meta["slot_candidates"])
        vector = sum(self.book.code("semantic_role", r) * self.book.code("value", meaning[r]) for r in ROLES)
        return {"schema": "plm-l1-component-meaning-v09", "model_fingerprint": self.fingerprint, "dimension": self.book.dimension,
                "real": vector.real.tolist(), "imag": vector.imag.tolist(), "eligible_for_inference": False}

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
            require(packet["schema"] == "plm-l1-component-meaning-v09" and packet["model_fingerprint"] == self.fingerprint, "packet_model_mismatch")
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
                require(top >= MIN_SCORE and top-runner >= MIN_MARGIN, "ambiguous_meaning")
                meaning[role] = self.meta["slot_candidates"][role][order[0]]
                clean += self.book.code("semantic_role", role) * self.book.code("value", meaning[role])
            residual = float(np.linalg.norm(vector-clean) / np.linalg.norm(clean))
            require(residual <= MAX_RESIDUAL, "meaning_residual_excessive")
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
            for i, block in enumerate(memory.blocks):
                key = name + "_" + str(i)
                groups[name].append({"weight": key})
                weights[key] = np.frombuffer(block.blob, dtype=np.uint8)
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
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            expected = {g["weight"] for groups in info["groups"].values() for g in groups}
            require(expected == set(weights.files), "invalid_weight_inventory")
            require(all(set(g) == {"weight"} for groups in info["groups"].values() for g in groups), "invalid_block_inventory")
            require(all(weights[k].dtype == np.uint8 and weights[k].ndim == 1 for k in expected), "invalid_block_encoding")
            memories = {name: BankedMemory([MemoryBlock(weights[g["weight"]].tobytes()) for g in groups]) for name, groups in info["groups"].items()}
        model = cls(meta, memories)
        require(model.fingerprint == info["fingerprint"], "model_hash_mismatch")
        return model
