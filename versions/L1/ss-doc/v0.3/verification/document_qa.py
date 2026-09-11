"""Check report figures and local evidence links without modifying frozen code."""
import re
import sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify

verify()
report=(ROOT/'REPORT.md').read_text(encoding='utf-8')
summary=read(ROOT/'verification/SUMMARY.json')
for row in summary['rows']:
    line='| {method} | {completed_correct} | {completed_wrong} | {needs_information} | {generated_correct} | {generated_wrong} |'.format(**row)
    assert line in report,line
assert summary['regression_correct']==summary['regression_cases']==144
assert read(ROOT/'examples/run/EXAMPLE.json')['after_restart']['text'] in report
assert '96照会中95件' in report and '960種類の独立した自然文書ではない' in report
assert '台帳の手前の生SS支持' in report and '結合型とラベル別型は同成績' in report
assert 'eligible_for_inference=false' in report
groups=defaultdict(list)
for row in read(ROOT/'verification/REVISION_COLLATERAL.json')['rows']:
    cond=row['condition'].split('-');groups[(int(cond[2][1:])*2,cond[3])].extend(row['queries'])
for (load,method),rows in groups.items():
    assert len(rows)==72
    line=f'| {load} | {method} | {sum(q["before_correct"] for q in rows)} | {sum(q["after_correct"] for q in rows)} | {sum(q["after_wrong"] for q in rows)} |'
    assert line in report,line
for file in ('FINAL_TESTS','DATA_AUDIT','PRESERVATION','RELEASE_VERIFY','AUDIT'):
    assert read(ROOT/f'verification/{file}.json')['passed']
assert 'Ran 32 tests' in read(ROOT/'verification/FINAL_TESTS.json')['stderr']
v=read(ROOT/'verification/RELEASE_VERIFY.json')
assert (v['full_repeat_equal_files'],v['memories_loaded'],v['primary_requeries_compared'],v['reference_arrays_compared'],v['isolated_generated'])==(207,80,80,66,2)
links=0
for name in ('README.md','REPORT.md','SPECIFICATION.md','verification/VALIDATION.md'):
    path=ROOT/name;content=path.read_text(encoding='utf-8')
    assert '\ufffd' not in content
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',content):
        if target.startswith(('https:','http:','#')):continue
        target=target.split('#')[0]
        assert (path.parent/target).exists(),(name,target)
        links+=1
result={'passed':True,'primary_table_rows':len(summary['rows']),
      'supplement_table_rows':len(groups),'markdown_files_checked':4,'local_links_checked':links,
      'scope':'Evidence figures, literal example, frozen source and local links; not independent scientific peer review.'}
destination=ROOT/'verification/DOCUMENT_QA.json'
if destination.exists():assert read(destination)==result
else:write(destination,result)
print({'passed':True,'primary_rows':len(summary['rows']),'supplement_rows':len(groups),'links':links},flush=True)
