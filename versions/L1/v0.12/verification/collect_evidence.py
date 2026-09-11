import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import sha, verify_freeze
from evaluate import write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repeat', required=True)
    a = parser.parse_args()
    repeated = Path(a.repeat)
    files = []
    for p in sorted((ROOT / 'results').rglob('*')):
        if not p.is_file() or p.name == 'PERFORMANCE.json':
            continue
        relative = p.relative_to(ROOT / 'results')
        original = sha(p)
        other = sha(repeated / relative)
        files.append({'file': relative.as_posix(), 'sha256': original, 'repeat_sha256': other, 'equal': original == other})
    assert all(f['equal'] for f in files)
    write(ROOT / 'verification/REPEATABILITY.json', {'source_freeze': verify_freeze(), 'two_full_numeric_runs': True,
                                                   'files': files, 'excluded': ['PERFORMANCE.json']})
    baseline = json.loads((ROOT / 'verification/PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
    changed = [name for name, digest in baseline['files'].items() if sha(ROOT.parent / name) != digest]
    assert not changed
    write(ROOT / 'verification/PRESERVATION_CHECK.json', {'previous_files': len(baseline['files']), 'all_preserved': not changed, 'changed': changed,
                                                        'shared_history_excluded': baseline['shared_history_excluded']})
    checked = json.loads((ROOT / 'verification/strict/VERIFICATION.json').read_text(encoding='utf-8'))
    for demo in checked['query_demos']:
        write(ROOT / 'examples' / (demo['name'] + '.json'), demo['context'])
    print(json.dumps({'equal_files': len(files), 'previous_files': len(baseline['files'])}))


if __name__ == '__main__':
    main()
