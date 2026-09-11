import copy
import hashlib
import math
import numpy as np
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import from_meaning, to_meaning, cell
from ss_partial.update import request, apply
from ss_partial.reader import read as read_text
from .oracle import localize, scored, render


def signal_hash(model, packet):
    return hashlib.sha256(model.vector(packet).astype('<c16').tobytes()).hexdigest()


def generate_scored(model, packet, meaning, order, goals):
    out = model.generate(packet, order, goals)
    result = {'order': order, 'goals': goals, 'generation': {k: v for k, v in out.items() if k != 'link_audit'},
              'score': None, 'reread_semantic_equal': False}
    if out['status'] == 'generated':
        ids = meaning['presentation'] if order == 'preserve' else list(reversed(meaning['presentation']))
        expected = localize(meaning, ids, goals)
        result['score'] = scored(expected, out['text'])
        again = model.document.read(out['text'])
        if again['status'] == 'read':
            got = model.document.recover(again['packet'])
            if got['status'] == 'recovered':
                localized = localize(got['meaning'], got['meaning']['presentation'], goals)
                result['reread_semantic_equal'] = localized['events'] == expected['events'] and localized['relations'] == expected['relations']
    return result


def trial(model, case):
    packet = model.encode(case['observation'])
    original = digest(packet)
    rec = model.recover(packet)
    inspection = model.inspect(packet)
    before = model.generate(packet)
    msg = request(packet, case['target'], case['teacher_value'])
    updated = apply(model, packet, msg)
    row = {'case_id': case['id'], 'state': case['observation']['cells'][case['target']]['state'],
           'count': case['observation']['count'], 'target': case['target'],
           'initial_signal_sha256': signal_hash(model, packet), 'recovery_status': rec['status'],
           'initial_observation_equal': rec.get('observation') == case['observation'],
           'inspection': inspection, 'generation_before': before,
           'teacher': msg, 'update': {k: v for k, v in updated.items() if k != 'packet'},
           'initial_packet_unchanged': original == digest(packet), 'outputs': [],
           'final_observation_equal': False, 'non_target_cells_equal': False, 'numeric_delta_equal': False}
    arrays = {'initial': model.vector(packet)}
    if 'packet' in updated:
        final = updated['packet']; recovered = model.recover(final)
        row['final_signal_sha256'] = signal_hash(model, final)
        row['final_observation_equal'] = recovered.get('observation') == case['expected_observation']
        if recovered['status'] == 'recovered':
            row['non_target_cells_equal'] = all(v == recovered['observation']['cells'][k] for k, v in case['observation']['cells'].items() if k != case['target'])
        delta = (model.codec.cell_vector(case['target'], case['expected_observation']['cells'][case['target']]) -
                 model.codec.cell_vector(case['target'], case['observation']['cells'][case['target']])) / math.sqrt(3.)
        row['numeric_delta_equal'] = bool(np.array_equal(model.vector(final), model.vector(packet) + delta))
        n = case['observation']['count']
        for order, goals in (('preserve', ['subject'] * n), ('reverse', ['object' if i % 2 == 0 else 'subject' for i in range(n)])):
            row['outputs'].append(generate_scored(model, final, case['expected_meaning'], order, goals))
        arrays['final'] = model.vector(final)
    return row, arrays


def transitions(model, case):
    known = case['expected_observation']; target = case['target']; truth = case['teacher_value']; other = case['alternate_value']
    rows = []
    def record(label, packet, message):
        original = digest(packet)
        out = apply(model, packet, message)
        result = {'label': label, 'message': message, 'source_signal_sha256': signal_hash(model, packet),
                  'update': {k: v for k, v in out.items() if k != 'packet'}, 'input_unchanged': digest(packet) == original}
        if 'packet' in out:
            result['inspection'] = model.inspect(out['packet'])
            result['generation'] = {k: v for k, v in model.generate(out['packet']).items() if k != 'link_audit'}
            result['observation'] = model.recover(out['packet']).get('observation')
            result['result_signal_sha256'] = signal_hash(model, out['packet'])
        rows.append(result)
        return out
    p = model.encode(known)
    conflict = record('known_disagreement', p, request(p, target, other))
    if 'packet' in conflict:
        q = conflict['packet']
        record('supply_does_not_resolve_conflict', q, request(q, target, truth))
        record('explicit_resolve', q, request(q, target, truth, 'resolve'))
    record('explicit_revise', p, request(p, target, other, 'revise'))
    partial = copy.deepcopy(known); partial['cells'][target] = cell('ambiguous', [truth, other])
    q = model.encode(partial)
    corrected = record('correct_supply', q, request(q, target, truth))
    if 'packet' in corrected:
        record('stale_replay', corrected['packet'], request(q, target, truth))
    record('unknown_value', q, request(q, target, '__unregistered__'))
    wrong = record('in_candidate_wrong_teacher', q, request(q, target, other))
    if 'packet' in wrong:
        rows[-1]['world_score'] = generate_scored(model, wrong['packet'], case['expected_meaning'], 'preserve', ['subject'] * known['count'])
    extra = next((v for v in model.codec.choices[target] if v not in (truth, other)), None)
    if extra is not None:
        record('outside_candidate_conflict', q, request(q, target, extra))
    return rows


def multi_step(model, meaning):
    known = from_meaning(meaning, model.codec.candidates)
    a, b = 'event:0/subject', 'event:1/polarity'
    o = copy.deepcopy(known); o['cells'][a] = cell('unobserved', []); o['cells'][b] = cell('unreadable', [])
    p = model.encode(o); first = apply(model, p, request(p, a, known['cells'][a]['candidates'][0]))
    result = {'initial_pending': model.inspect(p), 'first_update': {k: v for k, v in first.items() if k != 'packet'}}
    if 'packet' in first:
        q = first['packet']; result['after_one'] = model.generate(q)
        second = apply(model, q, request(q, b, known['cells'][b]['candidates'][0]))
        result['second_update'] = {k: v for k, v in second.items() if k != 'packet'}
        if 'packet' in second:
            result['final_observation_equal'] = model.recover(second['packet']).get('observation') == known
            result['final'] = generate_scored(model, second['packet'], meaning, 'reverse', ['subject'] * known['count'])
    return result


def corruptions(model, case):
    p = model.encode(case['observation']); v = model.vector(p); target = case['target']
    known = model.encode(case['expected_observation']); w = model.vector(known)
    truth = case['teacher_value']; other = case['alternate_value']
    basis = model.codec.values[target]; choices = model.codec.choices[target]
    rng = np.random.default_rng(92)
    variants = {'zero': np.zeros_like(v), 'half_erasure': v * (np.arange(len(v)) % 2),
                'noise_2': v + rng.normal(size=len(v)) * 2 + 2j * rng.normal(size=len(v)),
                'candidate_erasure': w - basis[choices.index(truth)] / math.sqrt(3.),
                'unannounced_extra_candidate': w + basis[choices.index(other)] / math.sqrt(3.)}
    return [{'label': name, 'signal_sha256': signal_hash(model, model.packet(value)),
             'recovery': {k: x for k, x in model.recover(model.packet(value)).items() if k != 'evidence'},
             'generation': {k: x for k, x in model.generate(model.packet(value)).items() if k != 'link_audit'}} for name, value in variants.items()]


def alternatives_trial(model, scene):
    known = from_meaning(scene['meaning'], model.codec.candidates)
    target = 'event:1/subject'
    excluded = {known['cells'][target]['candidates'][0], known['cells']['event:1/object']['candidates'][0]}
    other = next(v for v in model.codec.choices[target] if v not in excluded)
    changed = copy.deepcopy(scene['meaning']); changed['events'][1]['subject'] = other
    texts = [scene['text'], render(changed, ['subject'] * len(changed['events']))]
    out = read_text(model, texts)
    expected = copy.deepcopy(known); expected['cells'][target] = cell('ambiguous', [known['cells'][target]['candidates'][0], other])
    result = {'scene_id': scene['id'], 'texts': texts, 'read_status': out['status'], 'target': target}
    if 'packet' in out:
        expected = model.codec.encode(expected)
        result['signal_equal'] = bool(np.array_equal(model.vector(out['packet']), expected))
        result['generation_before'] = model.generate(out['packet'])
        update = apply(model, out['packet'], request(out['packet'], target, other))
        result['update_status'] = update['status']
        if 'packet' in update:
            result['final'] = generate_scored(model, update['packet'], changed, 'preserve', ['subject'] * len(changed['events']))
    return result
