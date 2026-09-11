"""Check report counts, example text and local links before sealing."""
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, verify


def main():
    frozen = verify(); summary = read(ROOT / 'verification/SUMMARY.json')
    report = (ROOT / 'REPORT.md').read_text(encoding='utf-8')
    for r in summary['primary']:
        label = '二事象' if r['count'] == 2 else '三事象'
        expected = f"| {label} | {r['inputs']} | {r['initial_exact']} | {r['final_exact']} | {r['non_target_unchanged']} | {r['generated_correct']} / {r['output_requests']} |"
        assert expected in report, expected
    example = read(ROOT / 'examples/EXAMPLE.json')
    assert example['after']['text'] in report and example['reverse']['text'] in report
    assert '外部で指定' in report and '長期学習' in report and '誤った教師' in report
    assert read(ROOT / 'verification/RELEASE_VERIFY.json')['passed']
    assert read(ROOT / 'verification/REPEATABILITY.json')['passed']
    links = []
    for path in ROOT.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'): continue
            filepart = target.split('#')[0].strip('<>')
            assert (path.parent / filepart).is_file(), (path, target)
            links.append({'document': path.relative_to(ROOT).as_posix(), 'target': target})
    write(ROOT / 'verification/DOCUMENT_QA.json', {'passed': True, 'frozen_source_digest': frozen,
          'primary_table_matches_saved_summary': True, 'examples_match_actual_generation': True,
          'relative_links_checked': links, 'scope': 'Text consistency, not a visual page-layout check.'})
    print({'passed': True, 'links': len(links)})


if __name__ == '__main__': main()
