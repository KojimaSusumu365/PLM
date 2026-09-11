import argparse
import time
import numpy as np
from ss_document.runtime import DocumentModel
from ss_partial.runtime import PartialModel
from ss_partial.contract import from_meaning
from ss_partial.reader import read as read_text
from evaluation.integrity import ROOT, read, write, verify
from evaluation.cases import cases, scenes
from evaluation.experiment import trial, transitions, multi_step, corruptions, alternatives_trial, generate_scored


def evaluate(out):
    freeze = verify(); start = time.perf_counter()
    out = __import__('pathlib').Path(out); out.mkdir(parents=True, exist_ok=False)
    primary_cases = cases('evaluation'); source_scenes = scenes('evaluation')
    write(out / 'CASES.json', primary_cases); write(out / 'SCENES.json', source_scenes)
    base = DocumentModel.load(ROOT / 'model/document')
    rows, model_specs, diagnostics, probes, arrays, regression = [], [], [], [], {}, []
    for seed in range(3):
        model = PartialModel(base, seed=f'partial-code-{seed}')
        mid = f's{seed}-8192-bound'; model.save(out / 'models' / mid)
        model_specs.append({'id': mid, 'fingerprint': model.fingerprint, 'dimension': 8192, 'mode': 'bound'})
        for index, case in enumerate(primary_cases):
            row, numeric = trial(model, case); row['model_id'] = mid; rows.append(row)
            count_offset = 0 if case['observation']['count'] == 2 else sum(c['observation']['count'] == 2 for c in primary_cases)
            if index - count_offset < 12:
                for key, value in numeric.items(): arrays[f'{mid}-{index}-{key}'] = value
            if (index + 1) % 84 == 0: print(f'{mid}: {index+1}/{len(primary_cases)}', flush=True)
        for n in (2, 3):
            selected = [c for c in primary_cases if c['observation']['count'] == n and c['scene_id'].endswith('/0')]
            representatives = [next(c for c in selected if c['target'] == target and c['observation']['cells'][target]['state'] == 'ambiguous')
                               for target in ('event:1/subject', 'event:0/polarity', 'time/event:0,event:1')]
            scene = next(s for s in source_scenes if len(s['meaning']['events']) == n)
            probes.append({'model_id': mid, 'count': n,
                           'transitions': [{'case_id': c['id'], 'rows': transitions(model, c)} for c in representatives],
                           'multi_step': multi_step(model, scene['meaning']),
                           'corruptions': corruptions(model, representatives[0])})
        probes.append({'model_id': mid, 'explicit_readings': [alternatives_trial(model, scene) for scene in source_scenes]})
        for dimension, mode in ((1024, 'bound'), (128, 'bound'), (8192, 'unbound_events'), (8192, 'drop_state')):
            other = PartialModel(base, dimension, f'partial-code-{seed}', mode)
            name = f's{seed}-{dimension}-{mode}'; other.save(out / 'models' / name)
            model_specs.append({'id': name, 'fingerprint': other.fingerprint, 'dimension': dimension, 'mode': mode})
            for n in (2, 3):
                selected = [c for c in primary_cases if c['observation']['count'] == n and c['scene_id'].endswith('/0')]
                # All fields and three states, only first scene of each count.
                for case in selected:
                    row, _ = trial(other, case); row['model_id'] = name; diagnostics.append(row)
        if seed == 0:
            for case in read(ROOT / 'data/doc_v01_regression.json'):
                result = read_text(model, [case['text']])
                r = {'case_id': case['id'], 'read_status': result['status'], 'complete_observation_equal': False}
                if 'packet' in result:
                    expected = from_meaning(case['meaning'], model.codec.candidates)
                    r['complete_observation_equal'] = model.recover(result['packet']).get('observation') == expected
                    n = len(case['meaning']['events'])
                    r['output'] = generate_scored(model, result['packet'], case['meaning'], 'reverse', ['object' if i % 2 == 0 else 'subject' for i in range(n)])
                regression.append(r)
    np.savez_compressed(out / 'REFERENCE_SIGNALS.npz', **arrays)
    write(out / 'EVALUATION.json', {'frozen_source_digest': freeze, 'models': model_specs, 'primary': rows,
                                   'diagnostics': diagnostics, 'probes': probes, 'regression': regression,
                                   'eligible_for_inference': False})
    write(out / 'PERFORMANCE.json', {'seconds': time.perf_counter() - start})
    print(f'COMPLETE primary={len(rows)} diagnostics={len(diagnostics)} models={len(model_specs)}', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); a = p.parse_args(); evaluate(a.out)
