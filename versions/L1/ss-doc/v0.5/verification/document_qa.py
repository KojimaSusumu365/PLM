import re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify

def table_row(g):
    p=g['primary'];c=g['cold'];method={'versioned_shared':'共有','versioned_pair':'共有＋保護'}[g['method']]
    return f"|{method}|{g['policy']}|{g['global_budget_per_stream']}|{g['actual_confirmations']}|{p['correct']} / {p['wrong']} / {p['held']}|{c['correct']} / {c['wrong']} / {c['held']}|"

def run():
    summary=read(ROOT/'verification/SUMMARY.json');report=(ROOT/'REPORT.md').read_text(encoding='utf-8');assert len(summary['groups'])==18
    for g in summary['groups']:
        assert table_row(g) in report
        for k in ('primary','cold'):
            r=g[k];assert r['episodes']==48 and r['correct']+r['wrong']+r['held']==48
    selective=[g for g in summary['groups'] if g['policy']=='ss_selective']
    for key,wanted in [('primary',(183,0,105,366)),('cold',(206,0,82,412))]:
        actual=tuple(sum(g[key][field] for g in selective) for field in ('correct','wrong','held','correct_outputs'))
        assert actual==wanted and sum(g[key]['reread_equal'] for g in selective)==wanted[3]
    shared=next(g for g in selective if g['method']=='versioned_shared' and g['global_budget_per_stream']==24)
    assert shared['matched_missing_baseline']['pending_targets']==73 and shared['cold']['pending_targets']==1
    assert summary['primary_failures']==31 and summary['cold_failures']==0
    assert summary['v04_regression']['confirmations']==summary['v04_regression']['cold_correct']==3
    v=read(ROOT/'verification/VERIFY.json')
    assert (v['full_repeat_equal_files'],v['reference_arrays_compared'],v['isolated_generated'])==(327,128,2)
    assert read(ROOT/'verification/FINAL_TESTS.json')['tests']==86
    assert read(ROOT/'verification/VERIFY.json')['passed'] and read(ROOT/'verification/LOG_AUDIT.json')['passed']
    assert read(ROOT/'verification/PRESERVATION.json')['passed'] and read(ROOT/'verification/CLI_WORKFLOW.json')['passed']
    checked={};links=0
    for name in ('README.md','SPECIFICATION.md','REPORT.md','verification/VALIDATION.md'):
        p=ROOT/name;text=p.read_text(encoding='utf-8');assert '\ufffd' not in text
        assert not any(token in text for token in ('TODO','TBD','{{','}}'))
        assert text.count('```')%2==0
        for link in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text):
            if '://' in link or link.startswith('#'):continue
            target=(p.parent/link.split('#')[0]).resolve();assert target.is_relative_to(ROOT) and target.exists(),(name,link)
            links+=1
        checked[name]=sha(p)
    for limitation in ('独立','確率','教師','保留','質問','真偽'):
        assert limitation in report
    result={'passed':True,'documents':checked,'local_links_checked':links,'all_18_table_rows_match_summary':True,
            'frozen_digest':verify(),'eligible_for_inference':False}
    write(ROOT/'verification/DOCUMENT_QA.json',result);print(result)

if __name__=='__main__':run()
