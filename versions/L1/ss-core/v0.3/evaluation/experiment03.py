import copy
import hashlib
import json
import time
import types
from pathlib import Path
import numpy as np
from ss_partial.runtime import PartialModel
from ss_partial.contract import from_meaning, cell
from ss_document.runtime import DocumentModel
from plm_l1_v09.component.runtime import Model as ComponentModel
from ss_core_v03.runtime import load, run_text
from ss_core_v03.waveform import Engine, ArrayPort, PILOT
from ss_core_v03.correction import generate_saved
from ss_core_v02.store import Store
from ss_core_v02.transaction import apply_packet
from ss_revision.memory import RevisionMemory
from bridge.carrier import encode
from bridge.runtime import receive
from .oracle import scored, localize

ROOT = Path(__file__).resolve().parents[1]
STYLES = [('preserve', ['subject', 'subject']), ('reverse', ['object', 'subject'])]

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n')

def score(case, result, order, goals):
    ids = case['meaning']['presentation']
    ids = list(reversed(ids)) if order == 'reverse' else ids
    check = scored(localize(case['meaning'], ids, goals), result.get('text'))
    correct = result['status'] == 'generated' and all(check.values())
    return {'correct': correct, 'held': result['status'] != 'generated',
            'wrong_text': result['status'] == 'generated' and not correct, 'checks': check}

def fault_port(condition, seed=0):
    calls = [0]
    def port(source, pilots, tag):
        call = calls[0]
        calls[0] += 1
        rng = np.random.default_rng(seed*100000+call)
        for tick, y, mask in ArrayPort(source, pilots, tag):
            if condition == 'phase':
                y *= np.exp(.73j)
            if condition == 'truncate' and tick == source.shape[1]+2*PILOT-1:
                return
            data = PILOT <= tick < PILOT+source.shape[1]
            if data and condition == 'noise1':
                y += rng.standard_normal(len(y))+1j*rng.standard_normal(len(y))
            if data and condition.startswith('zero:') and tag.split('/')[0] == condition.split(':')[1]:
                y[:] = 0
            if data and condition == 'zero_next_state' and tag.startswith('sentence_program/'):
                y[1] = 0
            yield tick, y, mask
    return port

def evaluate(output, split='evaluation'):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads((ROOT/'data/WAVE03_CORPUS.json').read_text(encoding='utf-8'))['splits'][split]
    legacy = PartialModel.load(ROOT/'model')
    wave_assoc, integrated = load(ROOT), load(ROOT)
    # Explicit ablation: streaming memories/codecs, legacy procedural writer.
    wave_assoc.document.generate = types.MethodType(DocumentModel.generate, wave_assoc.document)
    wave_assoc.document.base.component.generate = types.MethodType(ComponentModel.generate, wave_assoc.document.base.component)
    models = {'legacy': legacy, 'wave_associations': wave_assoc, 'integrated': integrated}
    rows = []
    started = time.perf_counter()
    for index, case in enumerate(corpus):
        for name, model in models.items():
            for style, (order, goals) in enumerate(STYLES):
                if name == 'legacy':
                    read = model.document.read(case['text'])
                    result = model.document.generate(read['packet'], order, goals) if read['status'] == 'read' else read
                else:
                    start = len(model.engine.trace)
                    result = run_text(model, case['text'], order, goals)
                    write(output/f'traces/main-{index}-{name}-{style}.json', model.engine.trace[start:])
                record = {'case': case['id'], 'method': name, 'style': style, 'input': case['text'],
                          'result': result, **score(case, result, order, goals)}
                rows.append(record)
        print(json.dumps({'progress': index+1, 'of': len(corpus), 'split': split}), flush=True)
    write(output/'MAIN.json', rows)
    faults = []
    conditions = ('phase', 'noise1', 'truncate', 'zero:roles', 'zero:lexical_write',
                  'zero:temporal_write', 'zero:sentence_program', 'zero:document_program', 'zero_next_state')
    for condition in conditions:
        # Same public scopes/seed, no fault labels provided to the receiver.
        engine = Engine(fault_port(condition, 17))
        model = load(ROOT, engine)
        for index, case in enumerate(corpus[:2]):
            start = len(engine.trace)
            result = run_text(model, case['text'], 'reverse', ['object', 'subject'])
            faults.append({'condition': condition, 'case': case['id'], 'result': result,
                           **score(case, result, 'reverse', ['object', 'subject'])})
            write(output/f'traces/fault-{condition.replace(":", "-")}-{index}.json', engine.trace[start:])
    write(output/'FAULTS.json', faults)
    partial, transport, correction = [], [], []
    model = load(ROOT)
    for index, case in enumerate(corpus[:2]):
        observation = from_meaning(case['meaning'], model.codec.candidates)
        for state in ('unobserved', 'ambiguous', 'conflict'):
            obs = copy.deepcopy(observation)
            target = 'event:1/subject'
            candidates = [] if state == 'unobserved' else list(model.codec.candidates['subject'][:2])
            obs['cells'][target] = cell(state, candidates)
            packet = model.encode(obs)
            rec = model.recover(packet)
            r = model.generate(packet)
            partial.append({'case': case['id'], 'state': state, 'observation_equal': rec.get('observation') == obs,
                            'status': r['status'], 'no_text': not r.get('text')})
        packet = model.encode(observation)
        wire = encode(model, packet, 'wave03/'+str(index), 'spread')
        reception = receive(model, wire, 'wave03/'+str(index), 'spread')
        r = model.generate(reception['packet'], 'reverse', ['object', 'subject']) if reception['status'] == 'received' else reception
        transport.append({'case': case['id'], 'reception_status': reception['status'], 'result': r,
                          **score(case, r, 'reverse', ['object', 'subject'])})
        scope = {'episode': 'wave03/'+case['id'], 'mutable': ['event:1/subject', 'time/event:0/event:1']}
        # Use a known-good two-target scope from the earlier public schema.
        scope['mutable'] = ['event:1/subject', next(k for k in observation['cells'] if k.startswith('time/'))]
        query = copy.deepcopy(observation)
        for target in scope['mutable']:
            query['cells'][target] = cell('unobserved', [])
        store = Store(RevisionMemory(model.codec.candidates))
        store, learning = apply_packet(model, store, scope, packet)
        store.save(output/f'stores/{index}')
        cold = Store.load(output/f'stores/{index}', model.codec.candidates)
        start = len(model.engine.trace)
        r = generate_saved(model, cold, scope, model.encode(query), 'reverse', ['object', 'subject'])
        correction.append({'case': case['id'], 'learning_status': learning['status'], 'result': r,
                           **score(case, r, 'reverse', ['object', 'subject']), 'cost': model.engine.stats(start)})
        write(output/f'traces/correction-{index}.json', model.engine.trace[start:])
    write(output/'PARTIAL.json', partial)
    write(output/'TRANSPORT.json', transport)
    write(output/'CORRECTION.json', correction)
    invalid = []
    for text in ('未知が花子を助けた。太郎が次郎を褒めた。',
                 '太郎が花子を食べた。次郎が美咲を助けた。',
                 'もし太郎が花子を助けた。次郎が美咲を褒めた。',
                 '太郎が花子が助けた。次郎が美咲を褒めた。'):
        r = run_text(model, text)
        invalid.append({'input': text, 'result': r, 'held': r['status'] != 'generated'})
    write(output/'INVALID.json', invalid)
    summary = {'split': split, 'main': {}, 'faults': {}, 'partial_preserved': sum(r['observation_equal'] and r['no_text'] for r in partial),
               'transport_correct': sum(r['correct'] for r in transport), 'correction_correct': sum(r['correct'] for r in correction),
               'invalid_held': sum(r['held'] for r in invalid)}
    for name in models:
        group = [r for r in rows if r['method'] == name]
        summary['main'][name] = {'requests': len(group), 'correct': sum(r['correct'] for r in group),
                                 'held': sum(r['held'] for r in group), 'wrong_text': sum(r['wrong_text'] for r in group),
                                 'ticks': sum(r['result'].get('cost', {}).get('ticks', 0) for r in group),
                                 'windows': sum(r['result'].get('cost', {}).get('windows', 0) for r in group)}
    for condition in conditions:
        group = [r for r in faults if r['condition'] == condition]
        summary['faults'][condition] = {'correct': sum(r['correct'] for r in group), 'held': sum(r['held'] for r in group), 'wrong_text': sum(r['wrong_text'] for r in group)}
    summary['paired_surface_equal'] = all(rows[i]['result'].get('text') == rows[i+2]['result'].get('text') == rows[i+4]['result'].get('text') for i in range(0, len(rows), 6)) and all(rows[i+1]['result'].get('text') == rows[i+3]['result'].get('text') == rows[i+5]['result'].get('text') for i in range(0, len(rows), 6))
    summary['primary_pass'] = all(g['correct'] == g['requests'] for g in summary['main'].values()) and summary['paired_surface_equal'] and summary['partial_preserved'] == 6 and summary['transport_correct'] == 2 and summary['correction_correct'] == 2 and summary['invalid_held'] == 4 and all(g['held'] == 2 for k, g in summary['faults'].items() if k not in ('phase', 'noise1'))
    write(output/'SUMMARY.json', summary)
    write(output/'PERFORMANCE.json', {'seconds': time.perf_counter()-started, 'not_a_fair_hardware_speed_comparison': True})
    return summary
