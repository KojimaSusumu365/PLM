"""Evaluator-independent transfer of existing learned skeletons into SS steps.

This is supervised structural transfer, NOT discovery of a grammar from raw text.
"""
import itertools
import numpy as np
from plm_l1_v09.component.features import START
from plm_l1_v09.component.lexicon import GOALS
from plm_l1_v09.component.algebra import require
from .program import Program

def fit(name, sequences, engine, dimension=8192):
    actions = sorted({action for _, sequence in sequences for action in sequence})
    states = max(len(sequence) for _, sequence in sequences)+1
    meta = {'schema': 'ss-wave-program-03', 'name': name, 'dimension': dimension,
            'seed': 'wave-program03/'+name, 'actions': actions, 'states': states,
            'fields': sorted(sequences[0][0])}
    program = Program(meta, np.zeros((2, dimension), complex), engine)
    rows = 0
    for fields, sequence in sequences:
        context = program.context(fields)
        for i, action in enumerate(sequence):
            key = context*program.states[i]
            target = np.array([program.actions[actions.index(action)], program.states[i+1]])
            # Explicit per-chip additive binding update, no complete sequence stored.
            for tick in range(dimension):
                program.weights[:, tick] += key[tick].conj()*target[:, tick]
            rows += 1
    return program, {'teaching_sequences': len(sequences), 'teaching_transitions': rows,
                     'write_ticks': rows*dimension, 'written_complex_coefficients': rows*dimension*2,
                     'persistent_weight_bytes': program.weights.nbytes}

def transfer(component, engine):
    sentence = []
    candidates = component.meta['slot_candidates']
    for goal, polarity, modality in itertools.product(GOALS, candidates['polarity'], candidates['modality']):
        fields = {'goal': goal, 'polarity': polarity, 'modality': modality}
        meaning = {r: choices[0] for r, choices in candidates.items()}
        meaning.update(polarity=polarity, modality=modality)
        actions = ['token:'+t for t in component.gap(meaning, goal, START)]
        for role in component.order(goal):
            actions.append('lexical:'+role)
            actions.extend('token:'+t for t in component.gap(meaning, goal, role))
        actions.append('stop')
        sentence.append((fields, actions))
    document = []
    for presentation in (['event:0', 'event:1'], ['event:1', 'event:0']):
        for order in ('preserve', 'reverse'):
            # Existing explicit presentation behavior is supplied as teacher data.
            identities = presentation if order == 'preserve' else list(reversed(presentation))
            document.append(({'presentation': presentation, 'order': order}, ['event:'+i for i in identities]+['stop']))
    a, aa = fit('sentence_program', sentence, engine)
    b, ba = fit('document_program', document, engine)
    require(a.meta['dimension'] == b.meta['dimension'], 'program_width')
    return (a, b), {'sentence': aa, 'document': ba, 'source': 'frozen_v09_learned_gaps_order_plus_explicit_document_order_teacher',
                     'grammar_discovery': False, 'sequences_saved_in_inference_model': False}
