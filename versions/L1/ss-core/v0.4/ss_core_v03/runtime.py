"""Read/generate integration. No training or evaluation imports.

Text segmentation, schema dictionaries, action dispatch and safety gates remain
ordinary software. Selection of lexical/grammatical associations and the next
generation action/state is supplied by sampled SS correlations.
"""
import copy
import json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.runtime import Model as ComponentModel, abstain
from plm_l1_v09.component.algebra import require, digest
from plm_l1_v09.component.lexicon import ROLES, GOALS, CONTENT
from plm_l1_v09.contract import write_context
from ss_document.runtime import DocumentModel
from ss_document.contract import IDS, pair_relation, local_time
from ss_partial.runtime import PartialModel
from .banked import WaveMemory
from .codecs import BasisScan, WaveDocumentCodec, WavePartialCodec, choose, residual
from .program import Program
from .waveform import Engine

class WaveComponent(ComponentModel):
    def __init__(self, original, engine, program):
        self.__dict__.update(original.__dict__)
        self.engine, self.program = engine, program
        self.memories = {name: WaveMemory(memory, engine, name) for name, memory in original.memories.items()}
        self.scan = BasisScan([(role, np.array([self.book.code('semantic_role', role)*self.book.code('value', value)
                                               for value in self.meta['slot_candidates'][role]])) for role in ROLES], engine, 'component_packet')

    def recover(self, packet):
        try:
            require(type(packet) is dict and set(packet) == {'schema', 'model_fingerprint', 'dimension', 'real', 'imag', 'eligible_for_inference'}, 'unexpected_packet_fields')
            require(packet['schema'] == 'plm-l1-component-meaning-v09' and packet['model_fingerprint'] == self.fingerprint, 'packet_model_mismatch')
            require(type(packet['dimension']) is int and packet['dimension'] == self.book.dimension and packet['eligible_for_inference'] is False, 'invalid_contract')
            for field in ('real', 'imag'):
                require(type(packet[field]) is list and len(packet[field]) == self.book.dimension and all(type(v) in (int, float) for v in packet[field]), 'invalid_signal_values')
            vector = np.asarray(packet['real'], float)+1j*np.asarray(packet['imag'], float)
            require(np.isfinite(vector).all() and np.max(abs(vector)) <= 32., 'invalid_signal')
            scores = self.scan.read(vector)
            meaning = {}
            for role in ROLES:
                i, _ = choose(scores[role], 'ambiguous_meaning')
                meaning[role] = self.meta['slot_candidates'][role][i]
            clean = np.asarray(self.encode(meaning)['real'])+1j*np.asarray(self.encode(meaning)['imag'])
            return {'status': 'recovered', 'meaning': meaning, 'residual': residual(vector, clean, 'meaning_residual_excessive'), 'eligible_for_inference': False}
        except (ValueError, TypeError, OverflowError) as e:
            return abstain(str(e), meaning=None)

    def generate(self, packet, goal='object'):
        try:
            require(goal in GOALS, 'unsupported_goal')
            rec = self.recover(packet)
            require(rec['status'] == 'recovered', rec.get('reason', 'recovery_failed'))
            meaning = rec['meaning']
            fields = {'goal': goal, 'polarity': meaning['polarity'], 'modality': meaning['modality']}
            state, tokens, audit, roles = self.program.start(), [], [], set()
            for _ in range(12):  # safety ceiling; SS memory must select stop
                action, state, detail = self.program.step(fields, state)
                audit.append({'action': action, **detail})
                if action == 'stop':
                    require(roles == set(CONTENT) and len(tokens) <= 9, 'incomplete_or_excessive_output')
                    return {'status': 'generated', 'text': ''.join(tokens), 'trace': audit, 'eligible_for_inference': False}
                if action.startswith('lexical:'):
                    role = action[len('lexical:'):]
                    require(role in CONTENT and role not in roles, 'invalid_lexical_action')
                    surface = self.memories['lexical_write'].recall({'meaning_value': meaning[role]})['value']
                    require(surface is not None and self.meta['kinds'].get(surface) in ('entity', 'predicate'), 'unknown_lexical_realization')
                    tokens.append(surface)
                    roles.add(role)
                elif action.startswith('token:'):
                    token = action[len('token:'):]
                    require(self.meta['kinds'].get(token) == 'marker', 'invalid_marker_action')
                    tokens.append(token)
                else:
                    raise ValueError('unknown_action')
            raise ValueError('ss_stop_not_selected')
        except (ValueError, TypeError) as e:
            return abstain(str(e))

class WaveDocument(DocumentModel):
    def __init__(self, original, engine, sentence_program, document_program):
        self.__dict__.update(original.__dict__)
        self.engine, self.program = engine, document_program
        self.base = copy.copy(original.base)
        self.base.component = WaveComponent(original.base.component, engine, sentence_program)
        self.base.memories = {name: WaveMemory(memory, engine, name) for name, memory in original.base.memories.items()}
        self.codec = WaveDocumentCodec(original.codec, engine)

    def generate(self, packet, order='preserve', goals=None):
        try:
            require(order in ('preserve', 'reverse'), 'order_goal')
            rec = self.recover(packet)
            require(rec['status'] == 'recovered', rec.get('reason', 'recovery_failed'))
            meaning = rec['meaning']
            require(len(meaning['events']) == 2, 'wave03_two_events_only')
            if goals is None:
                goals = ['subject', 'subject']
            require(type(goals) in (tuple, list) and len(goals) == 2 and all(g in GOALS for g in goals), 'per_event_goals')
            fields = {'presentation': meaning['presentation'], 'order': order}
            state = self.program.start()
            inventory = {e['id']: e for e in meaning['events']}
            texts, identities, audits = [], [], []
            for _ in range(4):
                action, state, detail = self.program.step(fields, state)
                audits.append({'action': action, **detail})
                if action == 'stop':
                    require(len(identities) == 2 and set(identities) == set(IDS[:2]), 'incomplete_document')
                    return {'status': 'generated', 'text': ''.join(texts), 'event_order': identities, 'program_audit': audits, 'eligible_for_inference': False}
                require(action.startswith('event:'), 'invalid_document_action')
                identity = action[len('event:'):]
                require(identity in inventory and identity not in identities, 'invalid_event_selection')
                marker = ''
                if identities:
                    r = pair_relation(meaning, identities[-1], identity)
                    rename = dict(zip(r['pair'], IDS[:2]))
                    context = write_context(local_time(r), [rename[identities[-1]], rename[identity]])
                    selected = self.base.memories['temporal_write'].recall(context)
                    require(selected['value'] is not None, 'unlearned_link_generation')
                    marker = json.loads(selected['value'])
                    require(type(marker) is str and marker in self.base.meta['training']['marker_inventory'], 'learned_marker_inventory')
                    audits[-1]['link'] = selected
                event = {r: inventory[identity][r] for r in ROLES}
                out = self.base.component.generate(self.base.component.encode(event), goals[len(identities)])
                require(out['status'] == 'generated', 'event_generation_failed:'+out.get('reason', 'unknown'))
                audits[-1]['sentence'] = out['trace']
                texts.append(marker+out['text'])
                identities.append(identity)
            raise ValueError('document_stop_not_selected')
        except (ValueError, TypeError) as e:
            return abstain(str(e))

class WavePartial(PartialModel):
    def __init__(self, original, document, engine):
        self.__dict__.update(original.__dict__)
        self.document, self.engine = document, engine
        self.codec = WavePartialCodec(original.codec, engine)

def integrate(original, programs, engine):
    sentence, document = programs
    doc = WaveDocument(original.document, engine, sentence, document)
    return WavePartial(original, doc, engine)

def load(root, engine=None):
    root = Path(root)
    engine = engine or Engine()
    original = PartialModel.load(root/'model')
    programs = tuple(Program.load(root/'programs'/name, engine) for name in ('sentence', 'document'))
    return integrate(original, programs, engine)

def run_text(model, text, order='preserve', goals=None):
    start = len(model.engine.trace)
    read = model.document.read(text)
    if read['status'] != 'read':
        return {'status': 'abstain', 'stage': 'read', 'reason': read.get('reason'), 'text': None, 'cost': model.engine.stats(start)}
    result = model.document.generate(read['packet'], order, goals)
    return {**result, 'cost': model.engine.stats(start), 'read_signal_verified': read.get('signal_verified', False)}
