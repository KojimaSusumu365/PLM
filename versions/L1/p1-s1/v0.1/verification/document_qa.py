import re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
docs=('README.md','REPORT.md','SPECIFICATION.md','CORPUS.md','verification/VALIDATION.md');links=0;hashes={}
for name in docs:
    p=ROOT/name;t=p.read_text(encoding='utf-8');assert '\ufffd' not in t and t.count('```')%2==0
    assert not re.search(r'\bTODO\b|\bTBD\b|\{\{',t)
    for url in re.findall(r'\]\(([^)]+)\)',t):
        if '://' in url or url.startswith('#'):continue
        q=(p.parent/url.split('#')[0]).resolve();assert q.is_relative_to(ROOT.resolve()) and q.exists(),url;links+=1
    hashes[name]=sha(p)
groups=read(ROOT/'results/SUMMARY.json');report=(ROOT/'REPORT.md').read_text(encoding='utf-8')
labels={'direct':'直結・チャネルなし','ss_estimated':'SS＋推定同期','repeat_estimated':'非拡散反復＋推定同期','ss_disabled':'SS＋同期無効','ss_oracle':'SS＋真値補正・評価専用'}
for method,label in labels.items():
    row='|'+label+'|'
    for condition in ('clean','offset_noise','partial25'):
        g=next(g for g in groups if (g['condition'],g['method'])==(condition,method));row+=f"{g['correct']}/{g['cases']}|"
    assert row in report,row
audit=read(ROOT/'verification/LOG_AUDIT.json');assert (audit['generated_outputs'],audit['held_documents'],audit['wrong_outputs'],audit['reference_arrays_exact'])==(632,72,0,16)
v=read(ROOT/'verification/VERIFY.json');assert v['full_repeat_equal_files']==1555 and v['representative_full_replays']==44 and v['isolated_generated']==2
assert read(ROOT/'verification/SEMANTIC_STATE_AUDIT.json')['passed']
assert read(ROOT/'verification/LEGACY_TESTS.json')['test_count']==275
assert all(read(ROOT/'verification'/n)['passed'] for n in ('VERIFY.json','LOG_AUDIT.json','FINAL_TESTS.json','FINAL_PRESERVATION.json','LEGACY_TESTS.json'))
assert read(ROOT/'results/DECISION.json')['passed']
for phrase in ('RF実機','非拡散反復','32フレーム','指定2項目','時間波形','12場面'):assert phrase in report,phrase
write(ROOT/'verification/DOCUMENT_QA.json',{'passed':True,'documents':hashes,'local_links_checked':links,
    'all15_main_table_cells_match_results':True,'failure_side_and_limitations_present':True,'frozen_digest':verify()})
print({'passed':True,'links':links,'table_cells':15},flush=True)
