"""Inference-only phase associative transducers.

Grammar decisions come from six fitted numerical memories. The generic executor
can capture, bind, emit, and stop; it contains no Japanese grammar productions.
Finite inventories, action semantics and resource bounds are explicit prior knowledge.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from .algebra import Book, Memory, canonical, digest, require

ROLES = ("subject", "object", "predicate", "polarity", "modality")
MEMORIES = ("lex_class", "lex_value", "surface", "read_action", "read_next", "write_action")


def reader_key(state, category, order_binding=True):
    return ([("read_state", state)] if order_binding else []) + [("category", category)]


def writer_key(goal, position, polarity, modality, order_binding=True):
    return ([("write_position", position)] if order_binding else []) + [
        ("goal", goal), ("control_polarity", polarity), ("control_modality", modality)]


def abstain(reason, **extra):
    return dict(status="abstain", reason=reason, eligible_for_inference=False, **extra)


class Model:
    def __init__(self, metadata, memories):
        self.meta = json.loads(canonical(metadata))
        require(self.meta.get("schema") == "plm-l1-model-v1", "wrong model schema")
        require(self.meta.get("eligible_for_inference") is False, "inference is not authorized")
        require(set(memories) == set(MEMORIES), "wrong memory inventory")
        require(set(self.meta["slot_candidates"]) == set(ROLES), "wrong slot inventory")
        self.book = Book(self.meta["dimension"], self.meta["seed"])
        self.memories = memories
        for memory in memories.values():
            require(memory.book.dimension == self.book.dimension and memory.book.seed == self.book.seed, "memory book mismatch")
        self.fingerprint = digest({"metadata": self.meta, "memories": {
            k: {"hash": hashlib.sha256(v.vector.astype("<c16").tobytes()).hexdigest(), "candidates": list(v.candidates)}
            for k, v in sorted(memories.items())}})
        self.surfaces = sorted(self.meta["token_surfaces"], key=lambda x: (-len(x), x))
        self.slot_basis = {r: np.array([self.book.code("value", c).conj() for c in self.meta["slot_candidates"][r]]) for r in ROLES}

    def recall(self, name, parts):
        return self.memories[name].recall(parts)

    def role(self, name):
        return self.book.code("semantic_role", name) if self.meta["role_binding"] else np.ones(self.book.dimension)

    def tokenize(self, text):
        require(type(text) is str and 0 < len(text) <= 256, "empty_or_oversized_input")
        tokens, offset = [], 0
        while offset < len(text):
            token = next((s for s in self.surfaces if text.startswith(s, offset)), None)
            require(token is not None, "unknown_token")
            tokens.append(token)
            require(len(tokens) < self.meta["max_tokens"], "token_capacity_exceeded")
            offset += len(token)
        return tokens + ["<EOS>"]

    def pack(self, vector):
        return {"schema": "plm-l1-meaning-v1", "model_fingerprint": self.fingerprint,
                "dimension": self.book.dimension, "real": vector.real.tolist(), "imag": vector.imag.tolist(),
                "eligible_for_inference": False}

    def unpack(self, packet):
        require(type(packet) is dict and set(packet) == {"schema", "model_fingerprint", "dimension", "real", "imag", "eligible_for_inference"}, "unexpected_packet_fields")
        require(packet["schema"] == "plm-l1-meaning-v1" and packet["model_fingerprint"] == self.fingerprint, "packet_model_mismatch")
        require(type(packet["dimension"]) is int and packet["dimension"] == self.book.dimension, "packet_dimension_mismatch")
        require(packet["eligible_for_inference"] is False, "inference_is_prohibited")
        for field in ("real", "imag"):
            values = packet[field]
            require(type(values) is list and len(values) == self.book.dimension, "invalid_signal_shape")
            require(all(type(v) in (int, float) for v in values), "invalid_signal_type")
        vector = np.array(packet["real"], dtype=float) + 1j * np.array(packet["imag"], dtype=float)
        require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32.0, "nonfinite_or_excessive_signal")
        return vector

    def read(self, text):
        try:
            tokens = self.tokenize(text)
        except ValueError as error:
            return abstain(str(error), packet=None, trace=[])
        q = self.meta["initial_state"]
        pending, occupied = None, set()
        vector = np.zeros(self.book.dimension, dtype=np.complex128)
        trace = []
        for index, token in enumerate(tokens):
            category = self.recall("lex_class", [("token", token)])
            value = self.recall("lex_value", [("token", token)])
            if category["value"] is None or value["value"] is None:
                return abstain("lexical_memory_unresolved", packet=None, trace=trace)
            parts = reader_key(q, category["value"], self.meta["order_binding"])
            action = self.recall("read_action", parts)
            nxt = self.recall("read_next", parts)
            trace.append({"position": index, "state": q, "category": category["value"], "action": action, "next": nxt})
            if action["value"] is None or nxt["value"] is None:
                return abstain("grammar_memory_unresolved", packet=None, trace=trace)
            a, q = action["value"], nxt["value"]
            additions = []
            if a == "capture":
                if pending is not None or not value["value"].startswith("entity:"):
                    return abstain("invalid_capture", packet=None, trace=trace)
                pending = value["value"]
            elif a.startswith("bind:"):
                role = a.split(":", 1)[1]
                if pending is None or role not in ("subject", "object"):
                    return abstain("invalid_binding", packet=None, trace=trace)
                additions.append((role, pending))
                pending = None
            elif a == "predicate":
                additions.append(("predicate", value["value"]))
            elif a.startswith("status:"):
                _, polarity, mode = a.split(":")
                additions += [("polarity", "polarity:" + polarity), ("modality", "modality:" + mode)]
            elif a == "stop":
                if index != len(tokens) - 1 or q != self.meta["terminal_state"] or occupied != set(ROLES) or pending is not None:
                    return abstain("incomplete_or_trailing_structure", packet=None, trace=trace)
                return {"status": "read", "reason": "controlled_language_observation", "packet": self.pack(vector),
                        "trace": trace, "eligible_for_inference": False}
            elif a != "noop":
                return abstain("unknown_primitive", packet=None, trace=trace)
            for role, content in additions:
                if role in occupied or content not in self.meta["slot_candidates"][role]:
                    return abstain("duplicate_or_invalid_slot", packet=None, trace=trace)
                vector += self.role(role) * self.book.code("value", content)
                occupied.add(role)
        return abstain("missing_stop", packet=None, trace=trace)

    def recover(self, packet):
        try:
            vector = self.unpack(packet)
        except (ValueError, TypeError, OverflowError) as error:
            return abstain(str(error), slots=None)
        slots, audit = {}, {}
        clean = np.zeros(self.book.dimension, dtype=np.complex128)
        for role in ROLES:
            scores = np.real(self.slot_basis[role] @ (vector * self.role(role).conj())) / self.book.dimension
            order = np.argsort(-scores, kind="stable")
            top, runner = float(scores[order[0]]), max(0., float(scores[order[1]]))
            audit[role] = {"score": round(top, 8), "margin": round(top - runner, 8)}
            if top < self.meta["minimum"] or top - runner < self.meta["margin"]:
                return abstain("ambiguous_meaning", slots=None, audit=audit)
            slots[role] = self.meta["slot_candidates"][role][order[0]]
            clean += self.role(role) * self.book.code("value", slots[role])
        residual = float(np.linalg.norm(vector - clean) / np.linalg.norm(clean))
        if residual > 0.20:
            return abstain("meaning_residual_excessive", slots=None, audit=audit, residual=residual)
        return {"status": "recovered", "slots": slots, "audit": audit, "residual": round(residual, 8), "eligible_for_inference": False}

    def generate(self, packet, goal="object_first"):
        if goal not in self.meta["goals"]:
            return abstain("unknown_generation_goal", text=None)
        decoded = self.recover(packet)
        if decoded["status"] != "recovered":
            return abstain(decoded["reason"], text=None)
        slots = decoded["slots"]
        trace, output = [], []
        emitted_roles = set()
        for position in range(self.meta["max_generation_steps"]):
            action = self.recall("write_action", writer_key(goal, position, slots["polarity"], slots["modality"], self.meta["order_binding"]))
            a = action["value"]
            trace.append({"position": position, "action": action})
            if a is None:
                return abstain("generation_memory_unresolved", text=None, trace=trace)
            if a == "stop":
                if emitted_roles != {"subject", "object", "predicate"}:
                    return abstain("incomplete_generation", text=None, trace=trace)
                return {"status": "generated", "text": "".join(output), "trace": trace, "eligible_for_inference": False}
            if a.startswith("slot:"):
                role = a.split(":", 1)[1]
                if role not in ("subject", "object", "predicate") or role in emitted_roles:
                    return abstain("invalid_generation_slot", text=None, trace=trace)
                content = slots[role]
                emitted_roles.add(role)
            elif a.startswith("emit:"):
                content = a.split(":", 1)[1]
            else:
                return abstain("unknown_generation_primitive", text=None, trace=trace)
            selected = self.recall("surface", [("meaning", content)])
            if selected["value"] is None or selected["value"] == "<EOS>":
                return abstain("surface_memory_unresolved", text=None, trace=trace)
            output.append(selected["value"])
        return abstain("generation_capacity_exceeded", text=None, trace=trace)

    def save(self, directory):
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        require(not (target / "model.json").exists() and not (target / "weights.npz").exists(), "model_output_exists")
        info = {"metadata": self.meta, "fingerprint": self.fingerprint,
                "candidates": {k: list(v.candidates) for k, v in self.memories.items()}}
        (target / "model.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        np.savez_compressed(target / "weights.npz", **{k: v.vector for k, v in self.memories.items()})

    @classmethod
    def load(cls, directory):
        target = Path(directory)
        info = json.loads((target / "model.json").read_text(encoding="utf-8"))
        require(set(info) == {"metadata", "fingerprint", "candidates"}, "invalid model envelope")
        meta = info["metadata"]
        book = Book(meta["dimension"], meta["seed"])
        with np.load(target / "weights.npz", allow_pickle=False) as weights:
            require(set(weights.files) == set(MEMORIES), "invalid weight names")
            memories = {k: Memory(book, weights[k], info["candidates"][k], meta["minimum"], meta["margin"]) for k in MEMORIES}
        model = cls(meta, memories)
        require(model.fingerprint == info["fingerprint"], "model_hash_mismatch")
        return model


def chip_roundtrip(model, packet, length=4):
    """Explicit balanced +/-1 chips, ideal alignment only; NOT S1 integration.

    Equal energy: chips[d,j] = meaning[d] * code[j] / sqrt(L).
    No truth offsets, sync, channel robustness, or RF claims.
    """
    require(type(length) is int and length >= 2 and length <= 64 and length % 2 == 0, "invalid chip length")
    vector = model.unpack(packet)
    code = np.tile(np.array([1., -1.]), length // 2)
    chips = vector[:, None] * code[None, :] / np.sqrt(length)
    recovered = np.sum(chips * code[None, :], axis=1) / np.sqrt(length)
    return model.pack(recovered), {"chip_count": int(chips.size), "chips_per_component": length,
                                  "input_energy": float(np.sum(np.abs(vector) ** 2)),
                                  "chip_energy": float(np.sum(np.abs(chips) ** 2)),
                                  "maximum_error": float(np.max(np.abs(vector - recovered))),
                                  "scope": "ideal_mapping_only_not_S1_receiver_integration"}
