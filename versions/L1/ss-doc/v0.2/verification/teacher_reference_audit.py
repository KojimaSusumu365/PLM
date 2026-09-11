"""Distinguish changed reference values from adding previously unspecified time."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, verify


verify(); ev = read(ROOT / 'results/EVALUATION.json')
cases = {c['id']: c for c in read(ROOT / 'results/CASES.json')}; rows = []
for probe in ev['probes']:
    for group in probe.get('transitions', []):
        case = cases[group['case_id']]
        for r in group['rows']:
            if r['label'] != 'in_candidate_wrong_teacher': continue
            extra_time = case['target'].startswith('time/') and case['teacher_value'] == 'unspecified'
            assert r['world_score']['score']['semantic_equal'] is False
            rows.append({'model_id': probe['model_id'], 'case_id': case['id'], 'target': case['target'],
                         'reference_value': case['teacher_value'], 'supplied_value': case['alternate_value'],
                         'category': 'addition_of_unstated_time_not_proven_false_world_fact' if extra_time else 'changed_subject_or_polarity_against_reference',
                         'generated_text': r['generation']['text']})
counts = {k: sum(r['category'] == k for r in rows) for k in sorted({r['category'] for r in rows})}
assert len(rows) == 18 and sorted(counts.values()) == [6, 12]
write(ROOT / 'verification/TEACHER_REFERENCE_AUDIT.json', {'passed': True, 'rows': rows, 'counts': counts,
      'note': 'Frozen evaluation names world_score/world_wrong compare only to reference semantic annotations. Six cases add a previously unspecified temporal relation, not demonstrate a factually false world relation. Preserve original outputs; do not count all18 as demonstrated false facts.'})
print(counts)
