import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import sha, verify_freeze
from plm_l1_v013.teaching import Session
from evaluate import write


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repeat', required=True)
    a = p.parse_args()
    repeated = Path(a.repeat)
    files = []
    for source in sorted((ROOT / 'results').rglob('*')):
        if not source.is_file() or source.name == 'PERFORMANCE.json':
            continue
        relative = source.relative_to(ROOT / 'results')
        digest = sha(source)
        other = sha(repeated / relative)
        files.append({'file': relative.as_posix(), 'sha256': digest, 'repeat_sha256': other, 'equal': digest == other})
    assert all(f['equal'] for f in files)
    write(ROOT / 'verification/REPEATABILITY.json', {'two_full_evaluations': True, 'source_freeze': verify_freeze(), 'files': files, 'excluded': ['PERFORMANCE.json']})
    baseline = json.loads((ROOT / 'verification/PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
    changed = [name for name, digest in baseline['files'].items() if sha(ROOT.parent / name) != digest]
    assert not changed
    write(ROOT / 'verification/PRESERVATION_CHECK.json', {'previous_files': len(baseline['files']), 'all_preserved': True, 'changed': changed, 'shared_history_excluded': baseline['shared_history_excluded']})
    result = json.loads((ROOT / 'results/EVALUATION.json').read_text(encoding='utf-8'))
    exact = {(r['task_id'], r['method'], r['acquisition_seed']): r for r in result['runs'] if r['backend'] == 'exact'}
    matched = []
    for ss in [r for r in result['runs'] if r['backend'] == 'ss']:
        symbolic = exact[ss['task_id'], ss['method'], ss['acquisition_seed']]
        trajectory = [(t['request']['id'], t['teacher_label']) for t in ss['trace']] == [(t['request']['id'], t['teacher_label']) for t in symbolic['trace']]
        def predictions(r):
            return [(s['budget'], s['labels_used'], s['candidate_masks'], [[(p['value'], p['reason'], p['possible_labels']) for p in stage['predictions']] for stage in s['stages']]) for s in r['snapshots']]
        matched.append({'task_id': ss['task_id'], 'method': ss['method'], 'dimension': ss['dimension'], 'code_seed': ss['code_seed'], 'acquisition_seed': ss['acquisition_seed'],
                        'teacher_ids_and_labels_equal': trajectory, 'discrete_predictions_and_masks_equal': predictions(ss) == predictions(symbolic)})
    write(ROOT / 'verification/SS_EXACT_COMPARISON.json', {'comparisons': matched, 'all_equal': all(r['teacher_ids_and_labels_equal'] and r['discrete_predictions_and_masks_equal'] for r in matched),
                                                        'scope': 'Posthoc equality audit, not an accuracy acceptance requirement or SS advantage claim.'})
    strict = json.loads((ROOT / 'verification/strict/VERIFICATION.json').read_text(encoding='utf-8'))
    q = strict['demos'][0]['context']
    before = Session.load(ROOT / 'results/hidden-b0')
    one = Session.load(ROOT / 'results/hidden-b1')
    full = Session.load(ROOT / 'results/hidden-b16')
    request = before.choose()
    tasks = {t['id']: t for t in json.loads((ROOT / 'data/evaluation.json').read_text(encoding='utf-8'))}
    task = tasks[result['saved_sessions']['hidden-b0']['task_id']]
    label = task['teacher_answers'][request['id']]
    assert one.model.predict(q)['value'] is not None
    write(ROOT / 'examples/query.json', q)
    write(ROOT / 'examples/pool.json', before.pool)
    write(ROOT / 'examples/EXPECTED.json', {'scope': 'Separate demo answers, never pass this file to selection.', 'first_request_id': request['id'],
                                          'first_teacher_label': label, 'before': before.model.predict(q), 'after_one': one.model.predict(q), 'after_full': full.model.predict(q)})
    print(json.dumps({'equal_files': len(files), 'preserved_files': len(baseline['files']), 'ss_exact_comparisons': len(matched), 'ss_exact_all_equal': all(r['teacher_ids_and_labels_equal'] and r['discrete_predictions_and_masks_equal'] for r in matched)}))


if __name__ == '__main__':
    main()
