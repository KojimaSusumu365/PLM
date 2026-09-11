import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'outputs/PLM-L1-SS-doc-v0.2'
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, freeze
from evaluation.cases import cases
from evaluation.experiment import trial
from ss_document.runtime import DocumentModel
from ss_partial.runtime import PartialModel


document = DocumentModel.load(ROOT / 'model/document')
default = PartialModel(document)
write(ROOT / 'model/partial.json', {'metadata': default.meta, 'fingerprint': default.fingerprint})
model = PartialModel(document, seed='partial-development')
rows = []
for index, case in enumerate(cases('development')):
    row, _ = trial(model, case)
    assert row['initial_observation_equal'] and row['generation_before']['status'] == 'needs_information'
    assert row['final_observation_equal'] and row['non_target_cells_equal'] and row['numeric_delta_equal'], row
    assert all(o['score'] and o['score']['semantic_equal'] and o['score']['goals_equal'] and o['reread_semantic_equal'] for o in row['outputs']), row
    rows.append(row)
    if (index+1) % 42 == 0: print(f'Development {index+1}/168', flush=True)
write(ROOT / 'verification/DEVELOPMENT.json', {'passed': True, 'rows': rows, 'note': 'No final-case threshold tuning.'})
p = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
assert p.returncode == 0, p.stderr
write(ROOT / 'verification/TESTS.json', {'passed': True, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
freeze()
print(json.dumps({'passed': True, 'development_inputs': len(rows), 'tests': 41, 'frozen': True}), flush=True)
