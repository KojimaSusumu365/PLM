"""Gather real examples, repeat-run evidence, preserved files and measured costs."""
import argparse
import importlib.util
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, sha, verify
from ss_partial.runtime import PartialModel
from ss_partial.update import apply, request


def main(work, verified):
    verify(); work, verified = Path(work), Path(verified); work.mkdir(parents=True, exist_ok=False)
    for src, dst in (('VERIFY.json', 'RELEASE_VERIFY.json'), ('REPEATABILITY.json', 'REPEATABILITY.json'), ('ISOLATED.json', 'ISOLATED.json')):
        write(ROOT / 'verification' / dst, read(verified / src))
    spec = importlib.util.spec_from_file_location('ssdoc02_demo', ROOT / 'examples/demo.py')
    demo = importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)
    record, packets = demo.demo()
    write(ROOT / 'examples/EXAMPLE.json', record)
    for name, packet in packets.items(): write(ROOT / 'examples' / (name + '.json'), packet)
    write(ROOT / 'examples/teacher.json', record['teacher'])
    model = PartialModel.load(ROOT / 'model')
    for packet in packets.values(): model.inspect(packet); model.generate(packet)
    assert apply(model, packets['pending'], record['teacher'])['status'] == 'updated'
    model.save(work / 'model_after_demo')
    before = {p.relative_to(ROOT / 'model').as_posix(): sha(p) for p in (ROOT / 'model').rglob('*') if p.is_file()}
    after = {p.relative_to(work / 'model_after_demo').as_posix(): sha(p) for p in (work / 'model_after_demo').rglob('*') if p.is_file()}
    assert before == after
    base = read(ROOT / 'verification/PREVIOUS_BASELINE.json'); old = ROOT.parent / base['release']
    actual = {p.relative_to(old).as_posix(): sha(p) for p in old.rglob('*') if p.is_file()}
    assert actual == base['files']; assert sha(old.with_name(old.name + '.zip')) == base['zip_sha256']
    assert all(sha(ROOT / rel) == value for rel, value in base['copied_source'].items())
    write(ROOT / 'verification/PRESERVATION.json', {'passed': True, 'prior_release_files_unchanged': len(actual),
          'prior_zip_sha256': base['zip_sha256'], 'copied_source_files_unchanged': len(base['copied_source']),
          'model_files_equal_after_inspection_update_generation': len(before), 'persistent_learning_not_performed': True})
    write(ROOT / 'verification/ENVIRONMENT.json', {'python': sys.version, 'platform': platform.platform(), 'numpy': np.__version__})
    timings = []
    for _ in range(7):
        t = time.perf_counter(); model.inspect(packets['pending']); a = time.perf_counter()
        apply(model, packets['pending'], record['teacher']); b = time.perf_counter()
        model.generate(packets['corrected']); c = time.perf_counter()
        timings.append({'inspect_seconds': a-t, 'update_seconds': b-a, 'generate_seconds': c-b})
    write(ROOT / 'verification/BENCHMARK.json', {'rows': timings,
          'medians': {k: statistics.median(r[k] for r in timings) for k in timings[0]},
          'storage': model.codec.storage() | {'generator_document_basis_bytes': model.document.codec.storage()['document_basis_bytes'],
                    'combined_designed_document_bases_bytes': model.codec.storage()['total_document_basis_bytes'] + model.document.codec.storage()['document_basis_bytes']},
          'packet_file_bytes': {k: (ROOT / 'examples' / (k + '.json')).stat().st_size for k in packets},
          'scope': '7 warm serial repetitions on three-event demo; no host CPU-load isolation; excludes full RSS, power, FLOPs and external teacher latency.'})
    p = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert p.returncode == 0, p.stderr
    write(ROOT / 'verification/FINAL_TESTS.json', {'passed': True, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    cli = []
    for args, exit_code in ((['inspect', '--packet', 'examples/pending.json'], 0),
                            (['generate', '--packet', 'examples/pending.json'], 2),
                            (['update', '--packet', 'examples/pending.json', '--message', 'examples/teacher.json', '--out', str(work / 'cli-corrected.json')], 0),
                            (['generate', '--packet', str(work / 'cli-corrected.json'), '--order', 'reverse'], 0)):
        cmd = [sys.executable, '-B', '-m', 'ss_partial', args[0], '--model', 'model', *args[1:]]
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        # inspect reports needs_information and deliberately uses exit code 2.
        expected = 2 if args[0] == 'inspect' else exit_code
        assert p.returncode == expected, p.stderr
        cli.append({'command': cmd, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    write(ROOT / 'verification/CLI.json', cli)
    print(__import__('json').dumps({'passed': True, 'example': record['after']['text'], 'prior_files': len(actual)}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--work', required=True); p.add_argument('--verified', required=True)
    a = p.parse_args(); main(a.work, a.verified)
