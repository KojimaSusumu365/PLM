"""Check numerical claims and relative Markdown links before sealing the release."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, verify


def main():
    freeze = verify()
    summary = read(ROOT / 'verification/SUMMARY.json')
    primary = {r['count']: r for r in summary['rows'] if r['stage'] == 'primary'}
    report = (ROOT / 'REPORT.md').read_text(encoding='utf-8')
    for n, unique, inputs, outputs in ((2, 36, 108, 648), (3, 108, 324, 1944)):
        row = primary[n]
        assert row['inputs'] == row['read_correct'] == inputs
        for k in ('generation_requests', 'generated_correct', 'goal_correct', 'reread_semantic_correct'):
            assert row[k] == outputs
        assert row['generated_wrong'] == row['generator_abstain'] == row['blocked_by_reader'] == 0
        label = '二事象' if n == 2 else '三事象'
        assert f'| {label} | {unique} | {inputs} | {inputs} | {outputs} | {outputs} | 0 / 0 |' in report
    example = read(ROOT / 'examples/EXAMPLES.json')[1]
    for name in ('README.md', 'REPORT.md'):
        content = (ROOT / name).read_text(encoding='utf-8')
        assert example['input'] in content and example['output'] in content
    assert read(ROOT / 'verification/RELEASE_VERIFY.json')['passed']
    assert read(ROOT / 'verification/EDGE_REVERSAL.json')['post_primary_supplement']
    assert 'unknown関係をbeforeへ変更' in report
    links = []
    for path in ROOT.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            filepart = target.split('#')[0].strip('<>')
            assert (path.parent / filepart).is_file(), (path, target)
            links.append({'document': path.relative_to(ROOT).as_posix(), 'target': target})
    write(ROOT / 'verification/DOCUMENT_QA.json', {
        'passed': True, 'frozen_source_digest': freeze, 'relative_links_checked': links,
        'primary_table_checked_against_saved_summary': True,
        'readme_report_example_exactly_matches_saved_output': True,
        'scope': 'Text and numerical consistency checks; no visual page-layout claim.'})
    print(json.dumps({'passed': True, 'links_checked': len(links)}))


if __name__ == '__main__':
    main()
