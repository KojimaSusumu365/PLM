"""Descriptive bookkeeping from frozen-evaluation output; no parameter selection."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, verify


def aggregate(rows):
    out = {key: 0 for key in ('inputs', 'initial_exact', 'correct_target_request', 'premature_generated',
                             'needs_information_before', 'initial_abstain', 'updated', 'update_rejected',
                             'final_exact', 'non_target_unchanged', 'local_delta_exact', 'source_unchanged',
                             'output_requests', 'output_executed', 'generated_correct', 'generated_wrong',
                             'generation_abstain', 'blocked_by_update', 'goals_correct', 'reread_correct')}
    for r in rows:
        out['inputs'] += 1
        out['initial_exact'] += r['initial_observation_equal']
        inspected = r['inspection']
        out['correct_target_request'] += inspected.get('status') == 'needs_information' and len(inspected['requests']) == 1 and inspected['requests'][0]['target'] == r['target']
        status = r['generation_before']['status']
        out['premature_generated'] += status == 'generated'
        out['needs_information_before'] += status == 'needs_information'
        out['initial_abstain'] += status == 'abstain'
        out['updated'] += r['update']['status'] == 'updated'
        out['update_rejected'] += r['update']['status'] == 'rejected'
        out['final_exact'] += r['final_observation_equal']
        out['non_target_unchanged'] += r['non_target_cells_equal']
        out['local_delta_exact'] += r['numeric_delta_equal']
        out['source_unchanged'] += r['initial_packet_unchanged']
        out['output_requests'] += 2
        out['output_executed'] += len(r['outputs'])
        out['blocked_by_update'] += 2 - len(r['outputs'])
        for g in r['outputs']:
            status = g['generation']['status']
            out['generation_abstain'] += status != 'generated'
            if status == 'generated':
                out['generated_correct' if g['score']['semantic_equal'] else 'generated_wrong'] += 1
                out['goals_correct'] += g['score']['goals_equal']
                out['reread_correct'] += g['reread_semantic_equal']
    return out


def main():
    verify(); ev = read(ROOT / 'results/EVALUATION.json')
    primary = [{'count': n, **aggregate([r for r in ev['primary'] if r['count'] == n])} for n in (2, 3)]
    per_state = [{'state': state, **aggregate([r for r in ev['primary'] if r['state'] == state])} for state in ('ambiguous', 'unobserved', 'unreadable')]
    diagnostic = []
    for dimension, mode in ((1024, 'bound'), (128, 'bound'), (8192, 'unbound_events'), (8192, 'drop_state')):
        for n in (2, 3):
            rs = [r for r in ev['diagnostics'] if r['count'] == n and r['model_id'].endswith(f'-{dimension}-{mode}')]
            diagnostic.append({'count': n, 'dimension': dimension, 'mode': mode, **aggregate(rs)})
    transitions, multiple, corruptions, readings = {}, [], [], []
    for p in ev['probes']:
        if 'explicit_readings' in p:
            readings.extend(p['explicit_readings']); continue
        multiple.append(p['multi_step']); corruptions.extend(p['corruptions'])
        for group in p['transitions']:
            for r in group['rows']:
                a = transitions.setdefault(r['label'], {'cases': 0, 'statuses': {}, 'no_complete_text': 0, 'world_correct': 0, 'world_wrong': 0})
                a['cases'] += 1; status = r['update']['status']; a['statuses'][status] = a['statuses'].get(status, 0) + 1
                a['no_complete_text'] += r.get('generation', {}).get('status') != 'generated'
                if 'world_score' in r and r['world_score']['score']:
                    a['world_correct' if r['world_score']['score']['semantic_equal'] else 'world_wrong'] += 1
    regression = ev['regression']
    result = {'primary': primary, 'primary_by_state': per_state, 'primary_total': aggregate(ev['primary']), 'diagnostics': diagnostic,
              'transitions': transitions, 'two_field_cases': len(multiple),
              'two_field_wait_after_one': sum(r.get('after_one', {}).get('status') == 'needs_information' for r in multiple),
              'two_field_final_exact': sum(r.get('final_observation_equal', False) for r in multiple),
              'two_field_generation_correct': sum(bool(r.get('final', {}).get('score', {}) and r['final']['score']['semantic_equal']) for r in multiple),
              'corruption_cases': len(corruptions), 'corruption_abstain': sum(r['generation']['status'] == 'abstain' for r in corruptions),
              'explicit_reading_cases': len(readings), 'explicit_reading_correct': sum(bool(r.get('final', {}).get('score', {}) and r['final']['score']['semantic_equal']) for r in readings),
              'regression_cases': len(regression), 'regression_read_correct': sum(r['complete_observation_equal'] for r in regression),
              'regression_generated_correct': sum(bool(r.get('output', {}).get('score', {}) and r['output']['score']['semantic_equal']) for r in regression),
              'regression_reread_correct': sum(r.get('output', {}).get('reread_semantic_equal', False) for r in regression),
              'unique_complete_scenes': len(read(ROOT / 'results/SCENES.json')), 'partial_cases_before_code_repetitions': len(read(ROOT / 'results/CASES.json')),
              'models': len(ev['models']), 'eligible_for_inference': False}
    write(ROOT / 'verification/SUMMARY.json', result)
    print(__import__('json').dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__': main()
