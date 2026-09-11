"""Numeric-packet-only inspection and complete generation; no reader/update imports."""
import json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import canonical, digest, require
from plm_l1_v09.component.runtime import abstain
from ss_document.runtime import DocumentModel, PACKET_FIELDS
from .codec import PartialCodec
from .contract import normalize, to_meaning, pending


class PartialModel:
    def __init__(self, document, dimension=8192, seed='partial-code-0', mode='bound'):
        require(isinstance(document, DocumentModel), 'document_model_required')
        self.document = document
        self.codec = PartialCodec(document.codec.candidates, dimension, seed, mode)
        self.meta = {'schema': 'plm-ss-partial-model-02', 'document_fingerprint': document.fingerprint,
                     'dimension': dimension, 'seed': seed, 'mode': mode, 'max_unresolved': 'bounded_by_2_or_3_event_schema',
                     'states': ['known', 'ambiguous', 'unobserved', 'unreadable', 'conflict'],
                     'persistent_learning': False, 'eligible_for_inference': False}
        self.fingerprint = digest(self.meta)

    def packet(self, vector):
        require(isinstance(vector, np.ndarray) and vector.shape == (self.codec.dimension,) and np.isfinite(vector).all(), 'vector')
        return {'schema': 'plm-ss-partial-signal-02', 'model_fingerprint': self.fingerprint,
                'dimension': self.codec.dimension, 'real': vector.real.tolist(), 'imag': vector.imag.tolist(),
                'eligible_for_inference': False}

    def vector(self, packet):
        require(type(packet) is dict and set(packet) == PACKET_FIELDS, 'unexpected_packet_fields')
        require(packet['schema'] == 'plm-ss-partial-signal-02' and packet['model_fingerprint'] == self.fingerprint, 'packet_model_mismatch')
        require(type(packet['dimension']) is int and packet['dimension'] == self.codec.dimension and packet['eligible_for_inference'] is False, 'packet_contract')
        for key in ('real', 'imag'):
            require(type(packet[key]) is list and len(packet[key]) == self.codec.dimension and all(type(v) in (float, int) for v in packet[key]), 'numeric_signal_only')
        vector = np.asarray(packet['real'], float).astype(complex)
        vector.imag = np.asarray(packet['imag'], float)
        require(np.isfinite(vector).all() and np.max(np.abs(vector)) <= 32., 'finite_bounded_signal')
        return vector

    def encode(self, observation):
        return self.packet(self.codec.encode(observation))

    def recover(self, packet):
        try:
            result = self.codec.recover(self.vector(packet))
            return {'status': 'recovered', **result, 'pending': pending(result['observation']), 'eligible_for_inference': False}
        except (ValueError, TypeError, OverflowError) as e:
            return abstain(str(e), observation=None)

    def inspect(self, packet):
        result = self.recover(packet)
        if result['status'] != 'recovered':
            return result
        return {'status': 'needs_information' if result['pending'] else 'ready',
                'packet_sha256': digest(packet), 'requests': result['pending'],
                'eligible_for_inference': False}

    def generate(self, packet, order='preserve', goals=None):
        try:
            result = self.recover(packet)
            require(result['status'] == 'recovered', result.get('reason', 'partial_recovery_failed'))
            if result['pending']:
                return {'status': 'needs_information', 'requests': result['pending'], 'eligible_for_inference': False}
            meaning = to_meaning(result['observation'], self.codec.candidates)
            return self.document.generate(self.document.encode(meaning), order, goals)
        except (ValueError, TypeError) as e:
            return abstain(str(e))

    def save(self, directory):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=False)
        self.document.save(path / 'document')
        (path / 'partial.json').write_text(canonical({'metadata': self.meta, 'fingerprint': self.fingerprint}) + '\n', encoding='utf-8')

    @classmethod
    def load(cls, directory):
        path = Path(directory)
        require({p.name for p in path.iterdir()} == {'document', 'partial.json'}, 'partial_model_inventory')
        obj = json.loads((path / 'partial.json').read_text(encoding='utf-8'))
        m = obj['metadata']
        result = cls(DocumentModel.load(path / 'document'), m['dimension'], m['seed'], m['mode'])
        require(result.meta == m and result.fingerprint == obj['fingerprint'], 'partial_model_fingerprint')
        return result
