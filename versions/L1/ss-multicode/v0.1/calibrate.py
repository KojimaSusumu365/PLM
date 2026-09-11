"""Development-only threshold selection. Never-taught labels are absence validation, not training."""
import argparse
import json
import platform
import sys
import time
import numpy as np
from ss_multicode.model import Model, SPECS
from ss_multicode.learning import Learner, teacher
from ss_multicode.algebra import digest
from evaluation.cases import stream
from evaluation.metrics import case_probes, subset, calibration_rows
from evaluation.integrity import ROOT, write


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); a = p.parse_args()
    from pathlib import Path
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=False)
    data = json.loads((ROOT / 'data/CASES.json').read_text(encoding='utf-8'))['development']
    arrays = {}; by_arch = {name: [] for name in SPECS}; records = []; start = time.perf_counter()
    for case in data:
        for architecture in SPECS:
            learner = Learner(Model(architecture, 'code-dev')); known = set()
            for block in stream(case, 'clean'):
                if block['phase'] not in ('A', 'B', 'C'): break
                for event in block['events']:
                    req = learner.question(event['context'])['request']
                    learner = learner.answer(req, teacher(req, event['teacher_label'])); known.add(event['id'])
                if block['epoch'] == 4:
                    rows, mask, truth = case_probes(case, known)
                    indexes = np.flatnonzero(mask | (np.arange(320) >= 192))
                    raw = learner.model.raw([r['context'] for r in rows]); raw = subset(raw, indexes)
                    prefix = f'd{len(records):03d}'
                    for key, values in raw.items(): arrays[prefix + '_' + key] = values
                    record = {'architecture': architecture, 'data_seed': case['seed'], 'phase': block['phase'],
                              'prefix': prefix, 'known': mask[indexes].tolist(), 'truth': truth[indexes].tolist(),
                              'teacher_presentations': learner.step, 'fingerprint': learner.fingerprint}
                    records.append(record); by_arch[architecture].append({'raw': raw, 'known': mask[indexes], 'truth': truth[indexes]})
            print('development', case['seed'], architecture, flush=True)
    selected = {}; grids = {}
    for architecture in SPECS:
        rows, best = calibration_rows(architecture, by_arch[architecture]); grids[architecture] = rows
        selected[architecture] = best
    report = {'schema': 'plm-ss-multicode-calibration-01', 'data_seeds': [c['seed'] for c in data],
              'code_seed': 'code-dev', 'scenario': 'clean', 'records': records, 'grid': grids, 'selected': selected,
              'absence_validation_is_extra_supervision': True, 'used_for_weight_updates': False,
              'selection_uses_evaluation_data': False, 'no_statistical_guarantee': True}
    report['digest'] = digest(report)
    write(out / 'CALIBRATION.json', report); np.savez_compressed(out / 'SCORES.npz', **arrays)
    write(out / 'PERFORMANCE.json', {'seconds': time.perf_counter() - start, 'python': sys.version, 'numpy': np.__version__, 'platform': platform.platform()})
    print(json.dumps({'records': len(records), 'teachers': len(data) * len(SPECS) * 768,
                      'selected': {k: {'policy': v['policy'], 'metrics': v['metrics']} for k, v in selected.items()}}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
