import re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify

def table_row(g):
    d=g['delayed'];method={'versioned_shared':'共有','versioned_pair':'共有＋保護'}[g['method']]
    return f"|{method}|{g['background_before']}→{g['background_after']}|{g['policy']}|{g['actual_confirmations']}|{g['immediate']['correct']}|{d['correct']} / {d['wrong']} / {d['held']}|"

def run():
    summary=read(ROOT/'verification/SUMMARY.json');report=(ROOT/'REPORT.md').read_text(encoding='utf-8');assert len(summary['groups'])==18
    for g in summary['groups']:
        assert table_row(g) in report
        assert g['actual_confirmations']==36 and g['candidate_scores']==774
        for key in ('immediate','delayed','baseline_before','baseline_delayed'):
            r=g[key];assert r['episodes']==72 and r['correct']+r['wrong']+r['held']==72
        d=g['delayed'];assert d['correct_text_documents']==d['correct'] and d['correct_outputs']==d['reread_equal']==2*d['correct']
        assert d['surface_valid']==d['goals_equal']==d['generated_outputs']
    for method,wanted in [('versioned_shared',{'rule':117,'random':110,'ss_learned':131}),('versioned_pair',{'rule':216,'random':216,'ss_learned':215})]:
        for policy,total in wanted.items():assert sum(g['delayed']['correct'] for g in summary['groups'] if g['method']==method and g['policy']==policy)==total
    audit=read(ROOT/'verification/LOG_AUDIT.json')
    assert (audit['actual_answers'],audit['required_answers'],audit['optional_answers'],audit['generated_outputs'],audit['wrong_outputs'])==(648,110,538,2010,0)
    checked_verify=read(ROOT/'verification/VERIFY.json')
    assert (checked_verify['full_repeat_equal_files'],checked_verify['selector_retraining_equal_files'],checked_verify['reference_arrays_compared'])==(907,6,195)
    for name in ('VERIFY','LOG_AUDIT','FINAL_TESTS','PRESERVATION','CLI_WORKFLOW','COMPUTE_COST'):
        assert read(ROOT/'verification'/(name+'.json'))['passed']
    checked={};links=0
    for name in ('README.md','SPECIFICATION.md','CORPUS.md','REPORT.md','verification/VALIDATION.md'):
        p=ROOT/name;text=p.read_text(encoding='utf-8');assert '\ufffd' not in text and text.count('```')%2==0
        assert not any(s in text for s in ('TODO','TBD','{{','}}'))
        for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text):
            if '://' in link or link.startswith('#'):continue
            target=(p.parent/link.split('#')[0]).resolve();assert target.is_relative_to(ROOT) and target.exists(),(name,link);links+=1
        checked[name]=sha(p)
    for limitation in ('独立','任意確認','線形','教師','保留','確率'):
        assert limitation in report
    result={'passed':True,'documents':checked,'local_links_checked':links,'all18_rows_match_results':True,'generated_texts_match_semantic_counts':True,
            'frozen_digest':verify(),'eligible_for_inference':False};write(ROOT/'verification/DOCUMENT_QA.json',result);print(result)

if __name__=='__main__':run()
