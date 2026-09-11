"""Independent release-document and post-hoc stress replay audit."""
import json
import re
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write,verify_freeze,sha
from ss_trace.runtime import State,choice,TRACE_MARGIN
from ss_trace.learning import teach
from ss_multicode.algebra import digest


def main():
    verify_freeze();summary=json.loads((ROOT/'verification/SUMMARY.json').read_text(encoding='utf-8'))
    rows={(r['size'],r['world'],r['arm'],r['checkpoint']):r['metrics'] for r in summary['rows']}
    m=rows[128,'stationary','main512_pair','post_E'];c=m['cohorts']['immediately_correct']
    assert c['n']==256 and c['teacher_aligned_failures']==15
    assert [c['detectors']['gap_drop']['last_teacher'][k] for k in ('tp','fn','fp')]==[14,1,108]
    assert [c['detectors']['ss_disagreement']['last_teacher'][k] for k in ('tp','fn','fp')]==[15,0,0]
    assert c['detectors']['ss_weak_support']['last_teacher']['fp']==16
    report=(ROOT/'REPORT.md').read_text(encoding='utf-8')
    table_rows=[]
    for arm,total in [('main512',32768),('main384_pair',32768),('main640',40960),('main512_pair',40960),('main512_bank',40960)]:
        old=rows[128,'stationary',arm,'post_E']['old']
        line=f"| {arm} | {total} | {old['accepted_correct']} | {old['accepted_wrong']} | {old['abstain']} |"
        assert line in report;table_rows.append(line)
    low=rows[64,'stationary','main512_pair','post_E']['cohorts']['immediately_correct']
    assert low['teacher_aligned_failures']==1 and low['detectors']['gap_drop']['last_teacher']['fp']==90
    d=rows[128,'drift_after_q16','main512_pair','post_E']['cohorts']['immediately_correct']
    assert [d['detectors']['ss_disagreement']['current_world'][k] for k in ('tp','fn','fp')]==[12,57,1]
    assert d['trace']['both_agree_obsolete']==56
    expected=json.loads((ROOT/'examples/EXPECTED.json').read_text(encoding='utf-8'))
    assert '_main512_pair_stationary' in expected['source_run']
    assert expected['before_observation']['ss_disagreement'] is True
    # Link targets in distributed Markdown must resolve locally unless web URLs.
    links=0
    for p in [ROOT/'README.md',ROOT/'REPORT.md',ROOT/'SPECIFICATION.md']:
        for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if not link.startswith(('https:','http:','#')):
                assert (p.parent/link).is_file(),(p,link);links+=1
    stress=json.loads((ROOT/'verification/STRESS.json').read_text(encoding='utf-8'))
    assert stress['plan']['script_sha256']==sha(ROOT/'verification/stress_trace.py')
    stress_states=0;replayed=0;teachers=0
    with np.load(ROOT/'verification/STRESS_SCORES.npz',allow_pickle=False) as arrays:
        for r in stress['rows']:
            s=State.load(ROOT/r['state']);raw=s.raw(r['contexts'])[1]
            np.testing.assert_array_equal(raw,arrays[r['array']]);stress_states+=1
            d=choice(raw);conf=(d['accepted']>=0)&(d['margin']>=TRACE_MARGIN);n=r['load'];truth=np.array(list(map(int,r['last_teacher'])))
            assert r['confident_correct']==int((conf[:n]&(d['accepted'][:n]==truth)).sum())
            assert r['confident_wrong']==int((conf[:n]&(d['accepted'][:n]!=truth)).sum())
            assert r['not_confident']==int((~conf[:n]).sum())
            assert r['unknown_confident']==int(conf[n:].sum())
            if r['stage']=='before_revision':
                fit=State(r['arm'],r['seed'])
                labels=[str(int(digest(['stress-truth',r['seed'],c])[:8],16)%4) for c in r['contexts'][:n]]
                for ctx,y in zip(r['contexts'][:n],labels):teach(fit,ctx,y);teachers+=1
                assert fit.fingerprint==s.fingerprint;replayed+=1
                for i in range(16):teach(fit,r['contexts'][i],str((int(labels[i])+1)%4));teachers+=1
                after=next(x for x in stress['rows'] if (x['seed'],x['arm'],x['load'],x['stage'])==(r['seed'],r['arm'],n,'after_revision'))
                assert fit.fingerprint==State.load(ROOT/after['state']).fingerprint;replayed+=1
    for n in (32,128,512):
        rr=[r for r in stress['rows'] if r['load']==n and r['arm']=='main512_pair' and r['stage']=='before_revision']
        line=f"| {n} | {4*n} | {sum(r['confident_correct'] for r in rr)} | {sum(r['confident_wrong'] for r in rr)} | {sum(r['not_confident'] for r in rr)} | {sum(r['unknown_confident'] for r in rr)} |"
        assert line in report;table_rows.append(line)
    write(ROOT/'verification/AUDIT.json',{'passed':True,'document_table_rows_checked':table_rows,'markdown_links_checked':links,
          'stress_states_recomputed':stress_states,'stress_states_replayed':replayed,'stress_replay_teachers':teachers,
          'core_contract_checks':'Primary confusion counts, drift false alarm, example provenance, frozen source.'})
    print(json.dumps({'passed':True,'stress_states':stress_states,'teachers':teachers,'table_rows':len(table_rows)}))


if __name__=='__main__':main()
