import re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,verify

verify();report=(ROOT/'REPORT.md').read_text(encoding='utf-8');summary=read(ROOT/'verification/SUMMARY.json')
for r in summary['rows']:
    line='| {method} | {correct} | {wrong} | {held} | {generated_correct} |'.format(**r)
    assert line in report,line
assert read(ROOT/'examples/run/EXAMPLE.json')['after_restart']['text'] in report
assert '1152種類の独立した文書ではない' in report and '等しいのは学習係数容量' in report
for name in ('FINAL_TESTS','CLI_WORKFLOW','PRESERVATION','RELEASE_VERIFY','AUDIT'):
    assert read(ROOT/f'verification/{name}.json')['passed']
data=read(ROOT/'verification/DATA_AUDIT.json')
assert data['completed'] and data['development_eval_disjoint'] and not data['strict_all_revision_scene_disjointness']
assert 'r200/10' in report and 'r201/230' in report and '完全分離' in report
assert 'Ran 62 tests' in read(ROOT/'verification/FINAL_TESTS.json')['stderr']
v=read(ROOT/'verification/RELEASE_VERIFY.json');assert v['memories_loaded']==v['primary_requeries_compared']==96
links=0
for name in ('README.md','REPORT.md','SPECIFICATION.md','verification/VALIDATION.md'):
    path=ROOT/name;content=path.read_text(encoding='utf-8');assert '\ufffd' not in content
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',content):
        if target.startswith(('http:','https:','#')):continue
        assert (path.parent/target.split('#')[0]).exists(),(name,target);links+=1
result={'passed':True,'primary_rows_checked':len(summary['rows']),'markdown_files':4,'links_checked':links,'data_overlap_disclosed':True,
        'scope':'Evidence figure and link checks;not independent scientific peer review.'}
path=ROOT/'verification/DOCUMENT_QA.json'
if path.exists():assert read(path)==result
else:write(path,result)
print(result,flush=True)
