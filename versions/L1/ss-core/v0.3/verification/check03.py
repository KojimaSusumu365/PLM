"""Release verifier; can run against an extracted, standalone archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n')

def frozen_files():
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(ROOT.rglob('*'))
            if p.is_file() and not set(p.relative_to(ROOT).parts)&{'results', 'development', 'verification', '__pycache__'}
            and (p.suffix == '.py' or p.relative_to(ROOT).parts[0] in ('data', 'model', 'programs') or p.name in ('PROTOCOL.json', 'requirements.txt'))}

def freeze():
    files = frozen_files()
    write(ROOT/'verification/FREEZE.json', {'files': files, 'sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()})

def run(output, repeat=None, verify_previous=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    record = json.loads((ROOT/'verification/FREEZE.json').read_text(encoding='utf-8'))
    assert record['files'] == frozen_files(), 'frozen_sources_changed'
    copied = json.loads((ROOT/'verification/PREVIOUS.json').read_text(encoding='utf-8'))
    for name, expected in copied['copied'].items():
        assert sha(ROOT/name) == expected, name
    if verify_previous:
        old = ROOT.parent/copied['source']
        assert {p.relative_to(old).as_posix(): sha(p) for p in old.rglob('*') if p.is_file()} == copied['previous_files']
        assert sha(old.with_name(old.name+'.zip')) == copied['previous_zip_sha256']
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
    write(output/'TESTS.json', {'returncode': tests.returncode, 'stdout': tests.stdout, 'stderr': tests.stderr})
    assert tests.returncode == 0, tests.stderr
    from evaluation.cases03 import build
    assert build() == json.loads((ROOT/'data/WAVE03_CORPUS.json').read_text(encoding='utf-8'))
    from ss_partial.runtime import PartialModel
    from ss_core_v03.runtime import load, run_text
    from ss_core_v03.training import transfer
    from ss_core_v03.waveform import Engine
    from ss_core_v03.program import Program
    import numpy as np
    base = PartialModel.load(ROOT/'model')
    programs, _ = transfer(base.document.base.component, Engine())
    for name, program in zip(('sentence', 'document'), programs):
        saved = Program.load(ROOT/'programs'/name, Engine())
        assert program.meta == saved.meta
        np.testing.assert_array_equal(program.weights, saved.weights)
    case = build()['splits']['evaluation'][0]
    model = load(ROOT)
    r = run_text(model, case['text'], 'reverse', ['object', 'subject'])
    rows = json.loads((ROOT/'results/MAIN.json').read_text(encoding='utf-8'))
    target = next(row for row in rows if row['case'] == case['id'] and row['method'] == 'integrated' and row['style'] == 1)
    assert r == target['result'], 'replayed_main_result'
    packet = base.document.read(case['text'])['packet']
    with tempfile.TemporaryDirectory(prefix='ss-wave03-isolated-') as temp:
        isolated = Path(temp)
        for package in ('plm_l1_v09', 'ss_document', 'ss_partial', 'ss_core_v03', 'model', 'programs'):
            for p in (ROOT/package).rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name not in ('reader.py', 'training.py', '__main__.py', 'correction.py'):
                    q = isolated/p.relative_to(ROOT)
                    q.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, q)
        write(isolated/'query.json', packet)
        command = "import json; from ss_core_v03.runtime import load; m=load('.'); p=json.load(open('query.json',encoding='utf-8')); print(json.dumps(m.document.generate(p,'reverse',['object','subject']),ensure_ascii=False))"
        child = subprocess.run([sys.executable, '-B', '-c', command], cwd=isolated, env=env, capture_output=True, text=True, encoding='utf-8')
        assert child.returncode == 0, child.stderr
        cold = json.loads(child.stdout)
        assert cold['text'] == r['text'] and cold['status'] == 'generated'
        isolated_record = {'generated': cold, 'reader_modules': 0, 'dedicated_training_modules': 0, 'evaluation_modules': 0,
                           'shared_modules_may_contain_unused_training_helpers': True, 'saved_input': 'numeric_semantic_packet'}
    write(output/'ISOLATED.json', isolated_record)
    # Saved correction artifacts load and can generate without teacher receipts.
    from ss_core_v02.store import Store
    from ss_core_v03.correction import generate_saved
    from ss_partial.contract import from_meaning, cell
    for index, item in enumerate(build()['splits']['evaluation'][:2]):
        obs = from_meaning(item['meaning'], model.codec.candidates)
        mutable = ['event:1/subject', next(k for k in obs['cells'] if k.startswith('time/'))]
        for key in mutable:
            obs['cells'][key] = cell('unobserved', [])
        store = Store.load(ROOT/f'results/stores/{index}', model.codec.candidates)
        out = generate_saved(model, store, {'episode': 'wave03/'+item['id'], 'mutable': mutable}, model.encode(obs), 'reverse', ['object', 'subject'])
        recorded = json.loads((ROOT/'results/CORRECTION.json').read_text(encoding='utf-8'))[index]
        assert out['text'] == recorded['result']['text']
    repeat_count = None
    if repeat:
        def inventory(path):
            return {p.relative_to(path).as_posix(): sha(p) for p in Path(path).rglob('*') if p.is_file() and p.name != 'PERFORMANCE.json'}
        first, second = inventory(ROOT/'results'), inventory(Path(repeat))
        assert first == second, 'repeat_results_differ'
        repeat_count = len(first)
    manifest_count = None
    manifest = ROOT/'verification/MANIFEST.json'
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        for name, expected in data.items():
            assert sha(ROOT/name) == expected, name
        actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p != manifest}
        assert actual == set(data), 'manifest_inventory'
        manifest_count = len(data)
    result = {'passed': True, 'frozen_files': len(record['files']), 'copied_files': len(copied['copied']),
              'previous_checked': verify_previous, 'repeat_identical_files': repeat_count,
              'manifest_files': manifest_count, 'cold_without_readers_trainers_evaluators': True,
              'retrained_programs_bitwise_equal': True, 'main_replay': 1, 'saved_correction_replays': 2,
              'python': sys.version, 'numpy': np.__version__}
    write(output/'VERIFY.json', result)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--output')
    parser.add_argument('--repeat')
    parser.add_argument('--previous', action='store_true')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        run(args.output, args.repeat, args.previous)
